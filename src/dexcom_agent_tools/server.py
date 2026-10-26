"""MCP server (stdio) exposing Dexcom Share glucose readings to agents.

Not a medical device. Do not use for treatment decisions.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .config import ConfigError, Settings, convert, normalize_units
from .source import SHARE_MAX_MINUTES, GlucoseSource, Reading, make_source
from .stats import compute_stats, to_units

DISCLAIMER = (
    "Data from the unofficial Dexcom Share API; may be delayed, missing or wrong. "
    "Not for treatment decisions - confirm with your receiver/app or a fingerstick."
)

mcp = MCPServer(
    name="dexcom",
    instructions=(
        "Read Dexcom CGM glucose via Dexcom Share. Only the last 24 hours are available. "
        "Times are ISO 8601; naive times are treated as the server's local time. " + DISCLAIMER
    ),
)


@lru_cache(maxsize=1)
def _settings() -> Settings:
    return Settings.from_env()


@lru_cache(maxsize=1)
def _source() -> GlucoseSource:
    return make_source(_settings())


def _get_source() -> GlucoseSource:
    try:
        return _source()
    except ConfigError as exc:
        raise ToolError(str(exc)) from exc


def _units(override: str | None) -> str:
    try:
        return normalize_units(override) if override else _settings().units
    except ConfigError as exc:
        raise ToolError(str(exc)) from exc


def _parse_time(value: str | None, default: datetime) -> datetime:
    if not value:
        return default
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ToolError(f"Invalid ISO 8601 timestamp: {value!r}") from exc
    return dt.astimezone() if dt.tzinfo is None else dt  # naive -> local time


def _fmt(r: Reading, units: str, now: datetime) -> dict:
    return {
        "time": r.time.astimezone().isoformat(timespec="seconds"),
        "value": convert(r.mg_dl, units),
        "units": units,
        "mg_dl": r.mg_dl,
        "trend": r.trend,
        "trend_arrow": r.trend_arrow,
        "trend_description": r.trend_description,
        "age_minutes": round((now - r.time).total_seconds() / 60, 1),
    }


def _window(start: str | None, end: str | None) -> tuple[datetime, datetime, datetime]:
    now = datetime.now(timezone.utc)
    end_dt = _parse_time(end, now)
    start_dt = _parse_time(start, end_dt - timedelta(hours=3))
    if start_dt >= end_dt:
        raise ToolError("start must be before end")
    oldest = now - timedelta(minutes=SHARE_MAX_MINUTES)
    if end_dt < oldest:
        raise ToolError("Dexcom Share only serves the last 24 hours; that window is older.")
    return max(start_dt, oldest), min(end_dt, now), now


def _readings_between(start_dt: datetime, end_dt: datetime, now: datetime) -> list[Reading]:
    minutes = int((now - start_dt).total_seconds() // 60) + 5
    try:
        readings = _get_source().recent(min(minutes, SHARE_MAX_MINUTES))
    except ToolError:
        raise
    except Exception as exc:  # pydexcom errors, network errors
        raise ToolError(f"Dexcom Share request failed: {exc}") from exc
    return [r for r in readings if start_dt <= r.time <= end_dt]


@mcp.tool()
def get_current_glucose(units: str | None = None) -> dict:
    """Latest CGM glucose reading with trend arrow and how old it is (minutes).

    units: "mg/dL" or "mmol/L" (defaults to DEXCOM_UNITS, else mg/dL).
    """
    u = _units(units)
    try:
        reading = _get_source().current()
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Dexcom Share request failed: {exc}") from exc
    if reading is None:
        return {"reading": None, "note": "No reading in the last 24 hours.", "disclaimer": DISCLAIMER}
    return {"reading": _fmt(reading, u, datetime.now(timezone.utc)), "disclaimer": DISCLAIMER}


@mcp.tool()
def get_glucose(start: str | None = None, end: str | None = None, units: str | None = None) -> dict:
    """CGM readings (every ~5 min, oldest first) between start and end.

    start/end: ISO 8601 timestamps; default is the last 3 hours. Dexcom Share only
    serves the last 24 hours, so the window is clipped to that.
    units: "mg/dL" or "mmol/L".
    """
    u = _units(units)
    start_dt, end_dt, now = _window(start, end)
    readings = _readings_between(start_dt, end_dt, now)
    return {
        "start": start_dt.astimezone().isoformat(timespec="seconds"),
        "end": end_dt.astimezone().isoformat(timespec="seconds"),
        "count": len(readings),
        "units": u,
        "readings": [_fmt(r, u, now) for r in readings],
        "disclaimer": DISCLAIMER,
    }


@mcp.tool()
def get_glucose_stats(
    start: str | None = None,
    end: str | None = None,
    target_low_mg_dl: float | None = None,
    target_high_mg_dl: float | None = None,
    units: str | None = None,
) -> dict:
    """Summary stats for a window: mean, SD, CV, GMI, min/max, and % time in/below/above range.

    start/end: ISO 8601 (default last 24 hours, the Share maximum).
    Target range defaults to DEXCOM_TARGET_LOW/HIGH (70-180 mg/dL). Thresholds are in mg/dL.
    Also reports very low (<54) and very high (>250). Percentages are by reading count.
    """
    u = _units(units)
    if start is None and end is None:
        now = datetime.now(timezone.utc)
        start = (now - timedelta(minutes=SHARE_MAX_MINUTES - 1)).isoformat()
    start_dt, end_dt, now = _window(start, end)
    low = target_low_mg_dl if target_low_mg_dl is not None else _settings().target_low
    high = target_high_mg_dl if target_high_mg_dl is not None else _settings().target_high
    if not 0 < low < high:
        raise ToolError("Need 0 < target_low_mg_dl < target_high_mg_dl")
    readings = _readings_between(start_dt, end_dt, now)
    stats = to_units(compute_stats([r.mg_dl for r in readings], low, high), u)
    expected = max(1, int((end_dt - start_dt).total_seconds() // 300))
    stats["coverage_percent"] = round(min(100.0, 100 * len(readings) / expected), 1)
    stats["start"] = start_dt.astimezone().isoformat(timespec="seconds")
    stats["end"] = end_dt.astimezone().isoformat(timespec="seconds")
    stats["disclaimer"] = DISCLAIMER
    return stats


def check() -> int:
    """Validate configuration (and in dry-run, print a sample) without starting the server."""
    try:
        settings = Settings.from_env()
        settings.require_credentials()
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    mode = "DRY RUN (synthetic data)" if settings.dry_run else f"Dexcom Share, region={settings.region}"
    print(f"Config OK: {mode}, units={settings.units}, target={settings.target_low:g}-{settings.target_high:g} mg/dL")
    if settings.dry_run:
        print(get_current_glucose())
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="dexcom-mcp", description="Dexcom Share MCP server (stdio)")
    parser.add_argument("--check", action="store_true", help="validate env config and exit")
    args = parser.parse_args(argv)
    if args.check:
        sys.exit(check())
    try:
        settings = Settings.from_env()
        settings.require_credentials()
    except ConfigError as exc:
        # Fail fast and loudly (stderr; stdout belongs to the MCP protocol).
        print(f"dexcom-mcp: {exc}", file=sys.stderr)
        sys.exit(2)
    mcp.run("stdio")


if __name__ == "__main__":
    main()
