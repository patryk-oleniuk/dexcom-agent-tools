"""Pure functions for glucose summary statistics. Inputs are mg/dL."""

from __future__ import annotations

import statistics
from collections.abc import Sequence

from .config import MGDL_PER_MMOL
VERY_LOW = 54
VERY_HIGH = 250


def compute_stats(values_mg_dl: Sequence[float], low: float = 70, high: float = 180) -> dict:
    """Mean, SD, CV, GMI and time-in-range percentages (by reading count)."""
    n = len(values_mg_dl)
    if n == 0:
        return {"count": 0}
    mean = statistics.fmean(values_mg_dl)
    sd = statistics.pstdev(values_mg_dl) if n > 1 else 0.0

    def pct(pred) -> float:
        return round(100 * sum(1 for v in values_mg_dl if pred(v)) / n, 1)

    return {
        "count": n,
        "mean_mg_dl": round(mean, 1),
        "sd_mg_dl": round(sd, 1),
        "cv_percent": round(100 * sd / mean, 1) if mean else None,
        # Glucose Management Indicator (Bergenstal 2018), estimate of A1c
        "gmi_percent": round(3.31 + 0.02392 * mean, 1),
        "min_mg_dl": min(values_mg_dl),
        "max_mg_dl": max(values_mg_dl),
        "target_low_mg_dl": low,
        "target_high_mg_dl": high,
        "tir_percent": pct(lambda v: low <= v <= high),
        "tbr_percent": pct(lambda v: v < low),
        "tbr_very_low_percent": pct(lambda v: v < VERY_LOW),
        "tar_percent": pct(lambda v: v > high),
        "tar_very_high_percent": pct(lambda v: v > VERY_HIGH),
    }


def to_units(stats: dict, units: str) -> dict:
    """Add unit-converted copies of the mg/dL fields when units are mmol/L."""
    if units != "mmol/L" or not stats.get("count"):
        return {**stats, "units": "mg/dL"}
    out = dict(stats)
    for key in list(stats):
        if key.endswith("_mg_dl") and stats[key] is not None:
            out[key.replace("_mg_dl", "_mmol_l")] = round(stats[key] / MGDL_PER_MMOL, 1)
    out["units"] = "mmol/L"
    return out
