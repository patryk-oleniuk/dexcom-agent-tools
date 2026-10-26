"""Settings loaded from environment variables only. Never hardcode credentials."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

MGDL_PER_MMOL = 18.0182
VALID_REGIONS = ("us", "ous", "jp")
VALID_UNITS = ("mg/dL", "mmol/L")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def normalize_units(raw: str | None) -> str:
    value = (raw or "mg/dL").strip().lower().replace(" ", "")
    if value in ("mg/dl", "mgdl", "mg"):
        return "mg/dL"
    if value in ("mmol/l", "mmol", "mmoll"):
        return "mmol/L"
    raise ConfigError(f"DEXCOM_UNITS must be one of {VALID_UNITS}, got {raw!r}")


@dataclass(frozen=True)
class Settings:
    username: str | None
    account_id: str | None
    password: str | None = field(repr=False)
    region: str = "us"
    units: str = "mg/dL"
    target_low: float = 70.0
    target_high: float = 180.0
    dry_run: bool = False

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        env = dict(os.environ if env is None else env)
        region = (env.get("DEXCOM_REGION") or "us").strip().lower()
        if region not in VALID_REGIONS:
            raise ConfigError(f"DEXCOM_REGION must be one of {VALID_REGIONS}, got {region!r}")
        try:
            low = float(env.get("DEXCOM_TARGET_LOW") or 70)
            high = float(env.get("DEXCOM_TARGET_HIGH") or 180)
        except ValueError as exc:
            raise ConfigError("DEXCOM_TARGET_LOW/HIGH must be numbers in mg/dL") from exc
        if not 0 < low < high:
            raise ConfigError("Need 0 < DEXCOM_TARGET_LOW < DEXCOM_TARGET_HIGH (mg/dL)")
        return cls(
            username=(env.get("DEXCOM_USERNAME") or "").strip() or None,
            account_id=(env.get("DEXCOM_ACCOUNT_ID") or "").strip() or None,
            password=env.get("DEXCOM_PASSWORD") or None,
            region=region,
            units=normalize_units(env.get("DEXCOM_UNITS")),
            target_low=low,
            target_high=high,
            dry_run=_truthy(env.get("DEXCOM_DRY_RUN")),
        )

    def require_credentials(self) -> None:
        """Fail clearly if credentials are missing (skipped in dry-run mode)."""
        if self.dry_run:
            return
        missing = []
        if not (self.username or self.account_id):
            missing.append("DEXCOM_USERNAME (or DEXCOM_ACCOUNT_ID)")
        if not self.password:
            missing.append("DEXCOM_PASSWORD")
        if missing:
            raise ConfigError(
                "Missing Dexcom credentials: "
                + ", ".join(missing)
                + ". Set them in the environment (see .env.example), "
                "or set DEXCOM_DRY_RUN=1 to use synthetic data."
            )


def convert(mg_dl: float, units: str) -> float:
    """Convert a mg/dL value to the requested units."""
    if units == "mmol/L":
        return round(mg_dl / MGDL_PER_MMOL, 1)
    return round(mg_dl) if float(mg_dl).is_integer() else round(mg_dl, 1)
