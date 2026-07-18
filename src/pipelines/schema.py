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
    "job_density", "distance_to_cbd_km", "job_accessibility",
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
_NON_NEGATIVE_COLUMNS = [
    "ttw_total", "total_pop", "pop_density", "stops_per_km2", "zori",
    "job_density", "distance_to_cbd_km", "job_accessibility",
]
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

    require_all_columns=True (default, pipeline write): all 35 REQUIRED_COLUMNS must exist.
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

    # One row per ZCTA is the dataset's core invariant: duplicated ZCTA5CE values
    # mean upstream row multiplication (e.g. double-fetched ZCTAs from overlapping
    # zip prefixes) and must fail loudly rather than reach analysis.
    if "ZCTA5CE" in df.columns:
        zctas = df["ZCTA5CE"].drop_nulls()
        n_dup_rows = zctas.len() - zctas.n_unique()
        if n_dup_rows > 0:
            dup_values = zctas.filter(zctas.is_duplicated()).unique().sort().to_list()
            errors.append(
                f"ZCTA5CE has {n_dup_rows} duplicate rows "
                f"(duplicated values, first 10: {dup_values[:10]})"
            )

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


# --- RQ4 panel products (additive; the 35-column contract above is untouched) ---

ZORI_PANEL_COLUMNS: list[str] = ["ZCTA5CE", "period", "zori"]
LODES_PANEL_COLUMNS: list[str] = ["ZCTA5CE", "year", "job_count", "job_accessibility"]
ACS_COMMUTE_2019_COLUMNS: list[str] = [
    "ZCTA5CE", "commute_min_proxy_2019", "ttw_total_2019",
]


def _zcta5_errors(df: pl.DataFrame) -> list[str]:
    """Shared ZCTA5CE checks for the panel validators: Utf8 dtype (a
    leading-zero code read without schema_overrides infers i64) and 5-digit
    zero-padded values."""
    if df["ZCTA5CE"].dtype != pl.Utf8:
        return [f"ZCTA5CE must be Utf8, got {df['ZCTA5CE'].dtype}"]
    bad_zcta = df["ZCTA5CE"].filter(
        df["ZCTA5CE"].is_null() | ~df["ZCTA5CE"].str.contains(r"^\d{5}$")
    )
    if bad_zcta.len() > 0:
        sample = bad_zcta.unique().sort().to_list()[:10]
        return [f"ZCTA5CE has {bad_zcta.len()} non-5-digit values (first 10: {sample})"]
    return []


def _dup_key_errors(df: pl.DataFrame, key_cols: list[str]) -> list[str]:
    """Duplicate-key check shared by the panel validators."""
    keys = df.select(key_cols)
    n_dup = keys.height - keys.unique().height
    if n_dup > 0:
        dup_sample = (
            keys.filter(keys.is_duplicated()).unique().sort(key_cols).head(10).rows()
        )
        return [
            f"{tuple(key_cols)} has {n_dup} duplicate key rows (first 10: {dup_sample})"
        ]
    return []


def validate_zori_panel(df: pl.DataFrame) -> list[str]:
    """Validate a zori_panel_<metro> frame; return error strings (empty = valid).

    Contract (design §1/§5): exact columns [ZCTA5CE, period, zori]; ZCTA5CE Utf8
    zero-padded 5-digit (read with schema_overrides={"ZCTA5CE": pl.Utf8}); period
    an ISO month-end date string (exactly Zillow's column labels); zori strictly
    positive and non-null — missing cells are absent rows, never nulls; no
    duplicate (ZCTA5CE, period) keys.
    """
    if list(df.columns) != ZORI_PANEL_COLUMNS:
        return [f"columns must be exactly {ZORI_PANEL_COLUMNS}, got {list(df.columns)}"]

    errors: list[str] = []

    if df["ZCTA5CE"].dtype != pl.Utf8:
        errors.append(f"ZCTA5CE must be Utf8, got {df['ZCTA5CE'].dtype}")
    else:
        bad_zcta = df["ZCTA5CE"].filter(
            df["ZCTA5CE"].is_null() | ~df["ZCTA5CE"].str.contains(r"^\d{5}$")
        )
        if bad_zcta.len() > 0:
            sample = bad_zcta.unique().sort().to_list()[:10]
            errors.append(
                f"ZCTA5CE has {bad_zcta.len()} non-5-digit values (first 10: {sample})"
            )

    if df["period"].dtype != pl.Utf8:
        errors.append(f"period must be Utf8 ISO date strings, got {df['period'].dtype}")
    else:
        parsed = df["period"].str.to_date("%Y-%m-%d", strict=False)
        bad_date = parsed.is_null()
        if bad_date.any():
            sample = df["period"].filter(bad_date).unique().sort().to_list()[:10]
            errors.append(
                f"period has {int(bad_date.sum())} non-ISO-date values (first 10: {sample})"
            )
        not_month_end = parsed.is_not_null() & (parsed != parsed.dt.month_end())
        if not_month_end.any():
            sample = df["period"].filter(not_month_end).unique().sort().to_list()[:10]
            errors.append(
                f"period has {int(not_month_end.sum())} non-month-end dates "
                f"(first 10: {sample})"
            )

    if not df["zori"].dtype.is_numeric():
        errors.append(f"zori must be numeric, got {df['zori'].dtype}")
    else:
        n_null = df["zori"].null_count()
        if n_null > 0:
            errors.append(
                f"zori has {n_null} null cells (missing cells must be absent rows, "
                "never nulls)"
            )
        nonpos = df["zori"].drop_nulls().filter(df["zori"].drop_nulls() <= 0)
        if nonpos.len() > 0:
            errors.append(f"zori must be > 0: {nonpos.len()} cells <= 0 (min={nonpos.min()})")

    keys = df.select(["ZCTA5CE", "period"])
    n_dup = keys.height - keys.unique().height
    if n_dup > 0:
        dup_sample = (
            keys.filter(keys.is_duplicated())
            .unique()
            .sort(["ZCTA5CE", "period"])
            .head(10)
            .rows()
        )
        errors.append(
            f"(ZCTA5CE, period) has {n_dup} duplicate key rows (first 10: {dup_sample})"
        )

    return errors


def validate_lodes_panel(df: pl.DataFrame) -> list[str]:
    """Validate a lodes_panel_<metro> frame; return error strings (empty = valid).

    Contract (design §1/§3/§5): exact columns [ZCTA5CE, year, job_count,
    job_accessibility]; ZCTA5CE Utf8 zero-padded 5-digit; year an integer
    within LODES_PANEL_YEARS; job_count integer (the gate byte-compares it —
    a float dtype would break append-only identity) non-null and >= 0;
    job_accessibility non-null and strictly > 0 (protects the log transform —
    a zero would be a high-leverage -inf); no duplicate (ZCTA5CE, year) keys.
    """
    from .lodes import LODES_PANEL_YEARS  # local: keep schema import light

    if list(df.columns) != LODES_PANEL_COLUMNS:
        return [f"columns must be exactly {LODES_PANEL_COLUMNS}, got {list(df.columns)}"]

    errors: list[str] = []
    errors.extend(_zcta5_errors(df))

    if not df["year"].dtype.is_integer():
        errors.append(f"year must be an integer dtype, got {df['year'].dtype}")
    else:
        bad_year = df["year"].filter(
            df["year"].is_null() | ~df["year"].is_in(list(LODES_PANEL_YEARS))
        )
        if bad_year.len() > 0:
            sample = bad_year.unique().sort().to_list()[:10]
            errors.append(
                f"year has {bad_year.len()} values outside LODES_PANEL_YEARS "
                f"{LODES_PANEL_YEARS[0]}-{LODES_PANEL_YEARS[-1]} (first 10: {sample})"
            )

    if not df["job_count"].dtype.is_integer():
        errors.append(
            f"job_count must be an integer dtype (gate byte-identity), "
            f"got {df['job_count'].dtype}"
        )
    else:
        n_null = df["job_count"].null_count()
        if n_null > 0:
            errors.append(f"job_count has {n_null} null cells")
        negative = df["job_count"].drop_nulls().filter(df["job_count"].drop_nulls() < 0)
        if negative.len() > 0:
            errors.append(
                f"job_count must be >= 0: {negative.len()} negative cells "
                f"(min={negative.min()})"
            )

    if not df["job_accessibility"].dtype.is_numeric():
        errors.append(
            f"job_accessibility must be numeric, got {df['job_accessibility'].dtype}"
        )
    else:
        n_null = df["job_accessibility"].null_count()
        if n_null > 0:
            errors.append(f"job_accessibility has {n_null} null cells")
        access = df["job_accessibility"].drop_nulls()
        nonpos = access.filter(access <= 0)
        if nonpos.len() > 0:
            errors.append(
                f"job_accessibility must be > 0 (log-transform guard): "
                f"{nonpos.len()} cells <= 0 (min={nonpos.min()})"
            )

    errors.extend(_dup_key_errors(df, ["ZCTA5CE", "year"]))
    return errors


def validate_acs_commute_2019(df: pl.DataFrame) -> list[str]:
    """Validate an acs_commute_2019_<metro> frame; return error strings.

    Contract (design §1/§3/§5): exact columns [ZCTA5CE, commute_min_proxy_2019,
    ttw_total_2019]; ZCTA5CE Utf8 zero-padded 5-digit, unique; proxy non-null
    with 0 < proxy < 180 (strict both ends); ttw_total_2019 integer, non-null,
    > 0 (zero-worker ZCTAs are dropped upstream by the division guard).
    """
    if list(df.columns) != ACS_COMMUTE_2019_COLUMNS:
        return [
            f"columns must be exactly {ACS_COMMUTE_2019_COLUMNS}, got {list(df.columns)}"
        ]

    errors: list[str] = []
    errors.extend(_zcta5_errors(df))

    proxy = df["commute_min_proxy_2019"]
    if not proxy.dtype.is_numeric():
        errors.append(f"commute_min_proxy_2019 must be numeric, got {proxy.dtype}")
    else:
        n_null = proxy.null_count()
        if n_null > 0:
            errors.append(
                f"commute_min_proxy_2019 has {n_null} null cells "
                "(zero-worker ZCTAs must be dropped, never null)"
            )
        vals = proxy.drop_nulls()
        out_of_range = vals.filter((vals <= 0) | (vals >= 180))
        if out_of_range.len() > 0:
            errors.append(
                f"commute_min_proxy_2019 must satisfy 0 < proxy < 180: "
                f"{out_of_range.len()} cells outside "
                f"(min={vals.min()}, max={vals.max()})"
            )

    total = df["ttw_total_2019"]
    if not total.dtype.is_integer():
        errors.append(f"ttw_total_2019 must be an integer dtype, got {total.dtype}")
    else:
        n_null = total.null_count()
        if n_null > 0:
            errors.append(f"ttw_total_2019 has {n_null} null cells")
        nonpos = total.drop_nulls().filter(total.drop_nulls() <= 0)
        if nonpos.len() > 0:
            errors.append(
                f"ttw_total_2019 must be > 0: {nonpos.len()} cells <= 0 "
                f"(min={nonpos.min()})"
            )

    errors.extend(_dup_key_errors(df, ["ZCTA5CE"]))
    return errors
