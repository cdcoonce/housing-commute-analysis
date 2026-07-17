"""Rebuild equivalence gate: compare regenerated final CSVs against a baseline.

Usage: uv run python scripts/rebuild_gate.py /tmp/hca_baseline [--accept-drift COL[,COL...]]

Passes when, for every metro:
  1. Row count and ZCTA set are identical to baseline.
  2. Every shared column EXCEPT the live ones ({zori, period, stops_per_km2})
     is byte-identical (string-level compare — same standard the Prefect
     refactor was held to).
  3. New columns are sane: job_density >= 0; min(distance_to_cbd_km) < 3 km
     (some ZCTA contains the CBD); Spearman corr(job_accessibility,
     distance_to_cbd_km) < 0 (access falls with distance).
Live-column drift is REPORTED (max abs delta) but does not fail the gate.

--accept-drift COL[,COL...] excludes the named columns from the frozen
byte-identity check in (2) above. For each accepted column, the number of
differing rows is reported instead of failing the gate. This is an escape
hatch for KNOWN, EXPLAINED divergences between the baseline and the current
pipeline code — it must never be used to silently paper over unexplained
drift.

Special case: if "income_segment" is in the accepted set, the gate performs
an additional verification per metro to prove the drift is exactly the
quartile-to-tercile boundary change in
``create_income_segments`` (src/pipelines/demographics.py):
  - Segments recomputed from the NEW csv's median_income using tercile
    boundaries (0.333 / 0.667) must equal the new csv's income_segment.
  - Segments recomputed from the BASELINE csv's median_income using quartile
    boundaries (0.25 / 0.75) must equal the baseline csv's income_segment.
If either recomputation fails to match, the gate FAILS for that metro —
accepting the column name alone is not sufficient proof; the drift must be
mechanically verified every run.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr

LIVE_COLUMNS = {"zori", "period", "stops_per_km2"}
NEW_COLUMNS = {"job_density", "distance_to_cbd_km", "job_accessibility"}
FINAL_DIR = Path(__file__).resolve().parents[1] / "data" / "final"

# Frozen NUMERIC columns tolerate last-ULP float differences (summation-order /
# numpy-version nondeterminism in tract->ZCTA aggregation, ~1e-16 relative).
# Any real data change is many orders of magnitude larger than this.
FLOAT_NOISE_RTOL = 1e-12


def _is_float_noise(base_col: pd.Series, new_col: pd.Series) -> bool:
    """True iff both columns are genuinely numeric and differ only within
    FLOAT_NOISE_RTOL. Non-numeric columns (coercion would fabricate NaNs)
    always return False and keep strict byte-identity."""
    import numpy as np

    base_num = pd.to_numeric(base_col, errors="coerce")
    new_num = pd.to_numeric(new_col, errors="coerce")
    if not (base_num.notna() == base_col.notna()).all():
        return False
    if not (new_num.notna() == new_col.notna()).all():
        return False
    return bool(
        np.isclose(
            base_num.to_numpy(dtype=float),
            new_num.to_numpy(dtype=float),
            rtol=FLOAT_NOISE_RTOL,
            atol=0.0,
            equal_nan=True,
        ).all()
    )


def _assign_income_segment(income: float, q_low: float, q_high: float) -> str | None:
    """Mirror the assignment rule in src/pipelines/demographics.py:259-267."""
    if pd.isna(income):
        return None
    elif income < q_low:
        return "Low"
    elif income <= q_high:
        return "Medium"
    else:
        return "High"


def _recompute_income_segment(median_income: pd.Series, q_low_quantile: float, q_high_quantile: float) -> pd.Series:
    q_low = median_income.quantile(q_low_quantile)
    q_high = median_income.quantile(q_high_quantile)
    return median_income.apply(lambda income: _assign_income_segment(income, q_low, q_high))


def verify_income_segment_drift(base: pd.DataFrame, new: pd.DataFrame) -> list[str]:
    """Prove income_segment drift is exactly the quartile->tercile boundary change.

    ``base`` and ``new`` must already be aligned (sorted, same ZCTA set) and
    contain string-typed median_income / income_segment columns.
    """
    errors: list[str] = []

    new_income = pd.to_numeric(new["median_income"], errors="coerce")
    recomputed_tercile = _recompute_income_segment(new_income, 0.333, 0.667)
    new_actual = new["income_segment"].where(new["income_segment"].notna(), None)
    if not recomputed_tercile.fillna("").equals(new_actual.fillna("")):
        errors.append(
            "income_segment: tercile recomputation from NEW median_income does not "
            "match NEW income_segment — drift is not explained by the boundary change"
        )

    base_income = pd.to_numeric(base["median_income"], errors="coerce")
    recomputed_quartile = _recompute_income_segment(base_income, 0.25, 0.75)
    base_actual = base["income_segment"].where(base["income_segment"].notna(), None)
    if not recomputed_quartile.fillna("").equals(base_actual.fillna("")):
        errors.append(
            "income_segment: quartile recomputation from BASELINE median_income does "
            "not match BASELINE income_segment — drift is not explained by the "
            "boundary change"
        )

    if not errors:
        print("    income_segment drift verified: quartile(baseline) -> tercile(new)")
    return errors


def check_metro(baseline_csv: Path, new_csv: Path, accept_drift: set[str]) -> list[str]:
    errors: list[str] = []
    base = pd.read_csv(baseline_csv, dtype=str)
    new = pd.read_csv(new_csv, dtype=str)

    if len(base) != len(new):
        errors.append(f"row count {len(base)} -> {len(new)}")
    if set(base["ZCTA5CE"]) != set(new["ZCTA5CE"]):
        errors.append("ZCTA set changed")
        return errors
    if len(base) != len(new):
        dup_base = int(base["ZCTA5CE"].duplicated().sum())
        dup_new = int(new["ZCTA5CE"].duplicated().sum())
        errors.append(
            "cannot compare frozen columns: row counts differ with equal ZCTA "
            f"sets (duplicated ZCTA5CE rows: baseline={dup_base}, new={dup_new})"
        )
        return errors

    base = base.sort_values("ZCTA5CE").reset_index(drop=True)
    new = new.sort_values("ZCTA5CE").reset_index(drop=True)

    frozen = [c for c in base.columns if c not in LIVE_COLUMNS]
    for col in frozen:
        if base[col].fillna("").equals(new[col].fillna("")):
            continue
        n_diff = int((base[col].fillna("") != new[col].fillna("")).sum())
        if col in accept_drift:
            print(f"    accepted drift {col}: {n_diff} rows differ")
            continue
        if _is_float_noise(base[col], new[col]):
            print(f"    float-noise drift {col}: {n_diff} rows differ at <= {FLOAT_NOISE_RTOL} relative")
            continue
        errors.append(f"frozen column '{col}' drifted in {n_diff} rows")

    if "income_segment" in accept_drift and "income_segment" in base.columns and "income_segment" in new.columns:
        errors.extend(verify_income_segment_drift(base, new))

    for col in LIVE_COLUMNS - {"period"}:
        b = pd.to_numeric(base[col], errors="coerce")
        n = pd.to_numeric(new[col], errors="coerce")
        delta = (b - n).abs().max()
        print(f"    live drift {col}: max |delta| = {delta}")

    num = pd.read_csv(new_csv)
    if (num["job_density"] < 0).any():
        errors.append("job_density has negative values")
    if num["distance_to_cbd_km"].min() >= 3.0:
        errors.append(
            f"min distance_to_cbd_km = {num['distance_to_cbd_km'].min():.1f} km "
            "(>= 3 km — CBD point is likely misplaced)"
        )
    rho = spearmanr(num["job_accessibility"], num["distance_to_cbd_km"]).statistic
    if rho >= 0:
        errors.append(f"job_accessibility does not fall with CBD distance (rho={rho:.2f})")
    print(f"    accessibility-vs-distance Spearman rho = {rho:.3f}")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild equivalence gate for final datasets.")
    parser.add_argument("baseline_dir", type=Path, help="Directory containing baseline final_zcta_dataset_*.csv files")
    parser.add_argument(
        "--accept-drift",
        default="",
        help="Comma-separated column names to exclude from the frozen byte-identity check",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline_dir: Path = args.baseline_dir
    accept_drift = {c.strip() for c in args.accept_drift.split(",") if c.strip()}
    failures: dict[str, list[str]] = {}
    for baseline_csv in sorted(baseline_dir.glob("final_zcta_dataset_*.csv")):
        metro = baseline_csv.stem.replace("final_zcta_dataset_", "")
        print(f"== {metro}")
        errs = check_metro(baseline_csv, FINAL_DIR / baseline_csv.name, accept_drift)
        if errs:
            failures[metro] = errs
            for e in errs:
                print(f"    FAIL: {e}")
        else:
            print("    OK")
    if failures:
        print(f"\nGATE FAILED for {sorted(failures)}")
        return 1
    print("\nGATE PASSED: all frozen columns identical, new columns sane.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
