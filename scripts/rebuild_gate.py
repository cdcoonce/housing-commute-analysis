"""Rebuild equivalence gate: compare regenerated final CSVs against a baseline.

Usage: uv run python scripts/rebuild_gate.py /tmp/hca_baseline

Passes when, for every metro:
  1. Row count and ZCTA set are identical to baseline.
  2. Every shared column EXCEPT the live ones ({zori, period, stops_per_km2})
     is byte-identical (string-level compare — same standard the Prefect
     refactor was held to).
  3. New columns are sane: job_density >= 0; min(distance_to_cbd_km) < 3 km
     (some ZCTA contains the CBD); Spearman corr(job_accessibility,
     distance_to_cbd_km) < 0 (access falls with distance).
Live-column drift is REPORTED (max abs delta) but does not fail the gate.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr

LIVE_COLUMNS = {"zori", "period", "stops_per_km2"}
NEW_COLUMNS = {"job_density", "distance_to_cbd_km", "job_accessibility"}
FINAL_DIR = Path(__file__).resolve().parents[1] / "data" / "final"


def check_metro(baseline_csv: Path, new_csv: Path) -> list[str]:
    errors: list[str] = []
    base = pd.read_csv(baseline_csv, dtype=str)
    new = pd.read_csv(new_csv, dtype=str)

    if len(base) != len(new):
        errors.append(f"row count {len(base)} -> {len(new)}")
    if set(base["ZCTA5CE"]) != set(new["ZCTA5CE"]):
        errors.append("ZCTA set changed")
        return errors

    base = base.sort_values("ZCTA5CE").reset_index(drop=True)
    new = new.sort_values("ZCTA5CE").reset_index(drop=True)

    frozen = [c for c in base.columns if c not in LIVE_COLUMNS]
    for col in frozen:
        if not base[col].fillna("").equals(new[col].fillna("")):
            n_diff = int((base[col].fillna("") != new[col].fillna("")).sum())
            errors.append(f"frozen column '{col}' drifted in {n_diff} rows")

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


def main() -> int:
    baseline_dir = Path(sys.argv[1])
    failures: dict[str, list[str]] = {}
    for baseline_csv in sorted(baseline_dir.glob("final_zcta_dataset_*.csv")):
        metro = baseline_csv.stem.replace("final_zcta_dataset_", "")
        print(f"== {metro}")
        errs = check_metro(baseline_csv, FINAL_DIR / baseline_csv.name)
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
