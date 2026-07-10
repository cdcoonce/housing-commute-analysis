"""Schema contract for the final ZCTA dataset (fail-fast on pipeline/analysis I/O)."""
from __future__ import annotations

import polars as pl

REQUIRED_COLUMNS: list[str] = [
    "ZCTA5CE", "rent_to_income", "pct_rent_burden_30", "pct_rent_burden_50", "zori",
    "commute_min_proxy", "pct_commute_lt10", "pct_commute_10_19", "pct_commute_20_29",
    "pct_commute_30_44", "pct_commute_45_59", "pct_commute_60_plus", "ttw_total",
    "pct_drive_alone", "pct_carpool", "pct_car", "pct_transit", "pct_walk", "pct_wfh",
    "renter_share", "vehicle_access", "total_pop", "pop_density", "pct_white",
    "pct_black", "pct_asian", "pct_hispanic", "pct_other", "median_income",
    "income_segment", "stops_per_km2", "period",
]

# Columns expressed as 0-100 percentages/shares.
# NOTE: vehicle_access is EXCLUDED — real committed data reaches 107-148 (it is a
# ratio of vehicles-to-something, not a bounded 0-100 percentage). Do not add it.
_PERCENT_COLUMNS = [
    "pct_rent_burden_30", "pct_rent_burden_50", "pct_commute_lt10", "pct_commute_10_19",
    "pct_commute_20_29", "pct_commute_30_44", "pct_commute_45_59", "pct_commute_60_plus",
    "pct_drive_alone", "pct_carpool", "pct_car", "pct_transit", "pct_walk", "pct_wfh",
    "renter_share", "pct_white", "pct_black", "pct_asian", "pct_hispanic", "pct_other",
]
# NOTE: median_income is EXCLUDED from non-negative checks — every committed dataset
# carries the Census "jam" sentinel (down to -666666666) for suppressed tracts. Do not add it.
_NON_NEGATIVE_COLUMNS = ["ttw_total", "total_pop", "pop_density", "stops_per_km2", "zori"]
_LOADER_CRITICAL = ["ZCTA5CE", "rent_to_income", "commute_min_proxy", "median_income", "stops_per_km2"]
_INCOME_SEGMENTS = {"Low", "Medium", "High"}
_PERCENT_TOL = 1.0  # allow tiny rounding overshoot past 100


def _range_violation(df: pl.DataFrame, col: str, lo: float, hi: float) -> str | None:
    if col not in df.columns:
        return None
    s = df[col].drop_nulls()
    if s.len() == 0:
        return None
    cmin, cmax = s.min(), s.max()
    if cmin < lo or cmax > hi:
        return f"{col} out of range [{lo}, {hi}]: min={cmin}, max={cmax}"
    return None


def validate_final_dataset(df: pl.DataFrame, *, require_all_columns: bool = True) -> None:
    """Raise ValueError if df violates the final-dataset contract. Nulls are ignored.

    require_all_columns=True (default, pipeline write): all 32 REQUIRED_COLUMNS must exist.
    require_all_columns=False (analysis load): only the loader-critical columns must exist;
      range checks apply to whichever bounded columns are present. This lets minimal test
      fixtures (fraction-unit shares, subset of columns) pass while still range-checking real data.
    """
    errors: list[str] = []

    if require_all_columns:
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"Schema violation: missing columns {missing}")
    else:
        missing = [c for c in _LOADER_CRITICAL if c not in df.columns]
        if missing:
            raise ValueError(f"Schema violation: missing critical columns {missing}")

    for col in _PERCENT_COLUMNS:
        errors.append(_range_violation(df, col, 0.0, 100.0 + _PERCENT_TOL))
    for col in _NON_NEGATIVE_COLUMNS:
        errors.append(_range_violation(df, col, 0.0, float("inf")))
    errors.append(_range_violation(df, "rent_to_income", 0.0, 2.0))
    errors.append(_range_violation(df, "commute_min_proxy", 0.0, 180.0))

    if "income_segment" in df.columns:
        seg = df["income_segment"].drop_nulls().unique().to_list()
        bad_seg = [s for s in seg if s not in _INCOME_SEGMENTS]
        if bad_seg:
            errors.append(f"income_segment has unexpected values: {bad_seg}")

    errors = [e for e in errors if e]
    if errors:
        raise ValueError("Schema violations: " + "; ".join(errors))
