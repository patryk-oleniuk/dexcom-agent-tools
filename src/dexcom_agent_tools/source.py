"""Glucose data sources: Dexcom Share (via pydexcom) and a synthetic dry-run source."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from .config import Settings

# Dexcom Share only serves the last 24 hours, one reading every 5 minutes.
SHARE_MAX_MINUTES = 1440
SHARE_MAX_COUNT = 288


@dataclass(frozen=True)
class Reading:
    time: datetime  # timezone-aware
    mg_dl: int
    trend: str  # e.g. "Flat", "SingleUp", "DoubleDown"
    trend_arrow: str
    trend_description: str


class GlucoseSource(Protocol):
    def current(self) -> Reading | None: ...

    def recent(self, minutes: int) -> list[Reading]:
        """Readings from the last `minutes` minutes, oldest first."""
        ...


class ShareSource:
    """Dexcom Share via pydexcom. Unofficial API; may break without notice."""

    def __init__(self, settings: Settings) -> None:
        settings.require_credentials()
        from pydexcom import Dexcom, Region  # imported lazily so dry-run needs no network

        kwargs = {"password": settings.password, "region": Region(settings.region)}
        if settings.account_id:
            kwargs["account_id"] = settings.account_id
        else:
            kwargs["username"] = settings.username
        self._dexcom = Dexcom(**kwargs)

    @staticmethod
    def _convert(r) -> Reading:
        return Reading(
            time=r.datetime,
            mg_dl=int(r.mg_dl),
            trend=r.trend_direction,
            trend_arrow=r.trend_arrow,
            trend_description=r.trend_description,
        )

    def current(self) -> Reading | None:
        # get_current_glucose_reading only returns a value from the last ~10 minutes;
        # fall back to the latest within 24h so the caller can judge staleness.
        r = self._dexcom.get_current_glucose_reading() or self._dexcom.get_latest_glucose_reading()
        return self._convert(r) if r else None

    def recent(self, minutes: int) -> list[Reading]:
        minutes = max(1, min(int(minutes), SHARE_MAX_MINUTES))
        readings = self._dexcom.get_glucose_readings(minutes=minutes, max_count=SHARE_MAX_COUNT)
        return sorted((self._convert(r) for r in readings), key=lambda x: x.time)


class FakeSource:
    """Deterministic synthetic CGM trace for DEXCOM_DRY_RUN=1 and tests."""

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now

    def _now_utc(self) -> datetime:
        return self._now or datetime.now(timezone.utc)

    def _trace(self) -> list[Reading]:
        now = self._now_utc().replace(second=0, microsecond=0)
        out = []
        for i in range(SHARE_MAX_COUNT, 0, -1):
            t = now - timedelta(minutes=5 * (i - 1))
            hour = t.hour + t.minute / 60
            mg = 130 + 45 * math.sin(hour / 24 * 2 * math.pi) + 25 * math.sin(i / 7)
            out.append(Reading(t, int(mg), "Flat", "→", "steady"))
        return out

    def current(self) -> Reading | None:
        return self._trace()[-1]

    def recent(self, minutes: int) -> list[Reading]:
        cutoff = self._now_utc() - timedelta(minutes=minutes)
        return [r for r in self._trace() if r.time >= cutoff]


def make_source(settings: Settings) -> GlucoseSource:
    return FakeSource() if settings.dry_run else ShareSource(settings)
