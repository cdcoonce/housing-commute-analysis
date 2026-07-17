"""Panel gate: compare regenerated RQ4 panel CSVs against a committed baseline.

Usage: uv run python scripts/panel_gate.py /path/to/baseline_dir \
    [--accept-revisions] [--accept-structural] [--accept-access-drift]

ZORI panel — snapshot-replace semantics (design doc §3,
docs/plans/2026-07-17-rq4-zori-dynamics-design.md): each rebuild replaces the
committed panel wholesale with one coherent Zillow vintage; this gate makes
revisions VISIBLE AND BOUNDED instead of pretending they don't happen. Per
metro, comparing baseline_dir/zori_panel_<metro>.csv against the regenerated
data/final/zori_panel_<metro>.csv.

Checks, with explicit denominators:
  1. Schema (NO escape hatch, ever — a malformed panel never lands): exact
     columns [ZCTA5CE, period, zori]; 5-digit ZCTA5CE; zori numeric, non-null
     (missing cells are absent rows, never nulls) and strictly positive; no
     duplicate (ZCTA5CE, period) keys.
  2. Lost months: the baseline's period set must be a subset of the new
     period set.
  3. ZCTA churn: |baseline ZCTAs absent from new| / |baseline ZCTAs| must be
     <= ZCTA_CHURN_MAX. Small churn is reported, not failed (Zillow
     occasionally retracts thin markets).
  4. Lost cells, computed over the INTERSECTION ZCTA set only (ZCTAs present
     in both baseline and new — otherwise churn that check 3 permits would
     mechanically trip this check): |baseline (ZCTA, period) cells absent
     from new, restricted to intersection ZCTAs| / |baseline cells of
     intersection ZCTAs| must be <= LOST_CELLS_MAX.

Revision policy (REPORT, bounded): over all overlapping (ZCTA, period) cells,
report the count of revised cells (|delta|/baseline > FLOAT_NOISE_RTOL) and
the median/p99/max of |delta|/baseline. FAIL only if more than
REVISED_CELLS_MAX of overlapping cells revise beyond REVISION_TOL, or any
single cell revises beyond REVISION_MAX_SINGLE.

Escape hatches (reviewed-HUMAN-only, mirroring rebuild_gate.py
--accept-drift; the PR that uses one must quote this gate's output):
  --accept-revisions    waives the revision-tolerance check only.
  --accept-structural   waives structural checks 2-4 (the deliberate-
                        rebaseline case: Zillow has retracted/truncated
                        history before). Prints exactly what it waived.
                        Schema check 1 is never waived.
  --accept-access-drift reserved for the LODES job_accessibility rtol check
                        (geometry-vintage case) — Phase 2.

LODES / ACS sections: Phase 2 stubs (filled by plan Task 12) — append-only
job_count byte-identity, job_accessibility at FLOAT_NOISE_RTOL, frozen ACS
2019 vintage.

Reads with dtype=str; numeric comparisons via pd.to_numeric (design §1),
exactly like rebuild_gate.py:127-128.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

ZCTA_CHURN_MAX = 0.05
LOST_CELLS_MAX = 0.01
REVISED_CELLS_MAX = 0.01
REVISION_TOL = 0.05
REVISION_MAX_SINGLE = 0.25
# Same value as rebuild_gate.py:47-49 — last-ULP float noise, not a revision.
FLOAT_NOISE_RTOL = 1e-12

ZORI_PANEL_COLUMNS = ["ZCTA5CE", "period", "zori"]
FINAL_DIR = Path(__file__).resolve().parents[1] / "data" / "final"


@dataclass
class GateResult:
    ok: bool
    errors: list[str]
    revision_report: dict[str, float]
    waived: list[str] = field(default_factory=list)


def _zori_schema_errors(new: pd.DataFrame) -> list[str]:
    """Check 1 — schema of the regenerated panel. Never waivable."""
    if list(new.columns) != ZORI_PANEL_COLUMNS:
        return [f"schema: columns must be exactly {ZORI_PANEL_COLUMNS}, got {list(new.columns)}"]
    errors: list[str] = []
    bad_zcta = ~new["ZCTA5CE"].astype(str).str.fullmatch(r"\d{5}")
    if bad_zcta.any():
        errors.append(f"schema: ZCTA5CE has {int(bad_zcta.sum())} non-5-digit values")
    zori = pd.to_numeric(new["zori"], errors="coerce")
    if zori.isna().any():
        errors.append(
            f"schema: zori has {int(zori.isna().sum())} null/non-numeric values "
            "(missing cells must be absent rows, never nulls)"
        )
    if (zori <= 0).any():
        errors.append(f"schema: zori has {int((zori <= 0).sum())} non-positive values")
    n_dup = int(new.duplicated(subset=["ZCTA5CE", "period"]).sum())
    if n_dup:
        errors.append(f"schema: {n_dup} duplicate (ZCTA5CE, period) keys")
    return errors


def check_zori_panel(
    baseline: pd.DataFrame,
    new: pd.DataFrame,
    accept_structural: bool = False,
    accept_revisions: bool = False,
) -> GateResult:
    """Gate one metro's regenerated ZORI panel against its committed baseline.

    Denominators (design §3): churn over |baseline ZCTAs|; lost cells over
    |baseline cells of the intersection ZCTA set|; revision fractions over
    |overlapping (ZCTA, period) cells|. ``accept_structural`` waives checks
    2-4 (never schema check 1); ``accept_revisions`` waives the revision-
    tolerance check only. Both are reviewed-human-only escape hatches: the PR
    that sets them must quote this gate's output, waived lines included.
    """
    schema_errors = _zori_schema_errors(new)
    if schema_errors:
        return GateResult(ok=False, errors=schema_errors, revision_report={})

    structural_errors: list[str] = []

    # Check 2: lost months.
    lost_months = sorted(set(baseline["period"]) - set(new["period"]))
    if lost_months:
        structural_errors.append(
            f"lost months: {len(lost_months)} baseline periods absent from new panel "
            f"(first 10: {lost_months[:10]})"
        )

    # Check 3: ZCTA churn (denominator: baseline ZCTAs).
    base_zctas = set(baseline["ZCTA5CE"])
    new_zctas = set(new["ZCTA5CE"])
    absent = base_zctas - new_zctas
    churn = len(absent) / len(base_zctas) if base_zctas else 0.0
    if churn > ZCTA_CHURN_MAX:
        structural_errors.append(
            f"ZCTA churn {churn:.1%} exceeds {ZCTA_CHURN_MAX:.0%} "
            f"({len(absent)} of {len(base_zctas)} baseline ZCTAs absent from new panel)"
        )
    elif absent:
        print(f"    churn (reported, within {ZCTA_CHURN_MAX:.0%}): {sorted(absent)}")

    # Check 4: lost cells over the INTERSECTION ZCTA set only (denominator:
    # baseline cells of intersection ZCTAs) — churn permitted by check 3 must
    # not mechanically trip this check.
    intersection = base_zctas & new_zctas
    base_int = baseline[baseline["ZCTA5CE"].isin(intersection)]
    base_cells = set(zip(base_int["ZCTA5CE"], base_int["period"]))
    new_cells = set(zip(new["ZCTA5CE"], new["period"]))
    lost = base_cells - new_cells
    lost_frac = len(lost) / len(base_cells) if base_cells else 0.0
    if lost_frac > LOST_CELLS_MAX:
        structural_errors.append(
            f"lost cells {lost_frac:.2%} exceeds {LOST_CELLS_MAX:.0%} over intersection "
            f"ZCTAs ({len(lost)} of {len(base_cells)} baseline cells absent from new panel)"
        )

    # Revision policy over overlapping cells: report, bounded.
    merged = baseline.merge(new, on=["ZCTA5CE", "period"], suffixes=("_base", "_new"))
    base_vals = pd.to_numeric(merged["zori_base"], errors="coerce")
    new_vals = pd.to_numeric(merged["zori_new"], errors="coerce")
    rel = (new_vals - base_vals).abs() / base_vals.abs()
    n_overlap = len(merged)
    revision_report: dict[str, float] = {
        "n_overlap": n_overlap,
        "n_revised": int((rel > FLOAT_NOISE_RTOL).sum()),
        "median": float(rel.median()) if n_overlap else 0.0,
        "p99": float(rel.quantile(0.99)) if n_overlap else 0.0,
        "max": float(rel.max()) if n_overlap else 0.0,
    }

    revision_errors: list[str] = []
    n_over_tol = int((rel > REVISION_TOL).sum())
    if n_overlap and n_over_tol / n_overlap > REVISED_CELLS_MAX:
        revision_errors.append(
            f"revisions: {n_over_tol} of {n_overlap} overlapping cells "
            f"({n_over_tol / n_overlap:.2%}) revised beyond {REVISION_TOL:.0%} "
            f"(limit {REVISED_CELLS_MAX:.0%} of cells)"
        )
    if n_overlap and revision_report["max"] > REVISION_MAX_SINGLE:
        revision_errors.append(
            f"single-cell revision {revision_report['max']:.1%} exceeds "
            f"{REVISION_MAX_SINGLE:.0%}"
        )

    errors: list[str] = []
    waived: list[str] = []
    if accept_structural:
        for e in structural_errors:
            waived.append(f"--accept-structural waived: {e}")
            print(f"    waived (--accept-structural): {e}")
    else:
        errors.extend(structural_errors)
    if accept_revisions:
        for e in revision_errors:
            waived.append(f"--accept-revisions waived: {e}")
            print(f"    waived (--accept-revisions): {e}")
    else:
        errors.extend(revision_errors)

    return GateResult(ok=not errors, errors=errors, revision_report=revision_report, waived=waived)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gate for committed RQ4 panel data products.")
    parser.add_argument(
        "baseline_dir", type=Path, help="Directory containing baseline zori_panel_*.csv files"
    )
    parser.add_argument(
        "--accept-revisions",
        action="store_true",
        help="Waive the ZORI revision-tolerance check (reviewed-human-only; quote gate output in the PR)",
    )
    parser.add_argument(
        "--accept-structural",
        action="store_true",
        help="Waive ZORI structural checks 2-4, never schema (reviewed-human-only; quote gate output in the PR)",
    )
    parser.add_argument(
        "--accept-access-drift",
        action="store_true",
        help="Waive the LODES job_accessibility rtol check (Phase 2; reviewed-human-only)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline_dir: Path = args.baseline_dir
    failures: dict[str, list[str]] = {}

    baselines = sorted(baseline_dir.glob("zori_panel_*.csv"))
    if not baselines:
        print(f"No zori_panel_*.csv baselines found in {baseline_dir}")
        return 1
    for baseline_csv in baselines:
        metro = baseline_csv.stem.replace("zori_panel_", "")
        print(f"== {metro} (zori panel)")
        new_csv = FINAL_DIR / baseline_csv.name
        if not new_csv.exists():
            failures[metro] = [f"regenerated panel missing: {new_csv}"]
            print(f"    FAIL: regenerated panel missing: {new_csv}")
            continue
        baseline = pd.read_csv(baseline_csv, dtype=str)
        new = pd.read_csv(new_csv, dtype=str)
        result = check_zori_panel(
            baseline,
            new,
            accept_structural=args.accept_structural,
            accept_revisions=args.accept_revisions,
        )
        report = result.revision_report
        if report:
            print(
                f"    revisions: {report['n_revised']}/{report['n_overlap']} overlapping "
                f"cells beyond float noise; |delta|/baseline median={report['median']:.2e} "
                f"p99={report['p99']:.2e} max={report['max']:.2e}"
            )
        if result.errors:
            failures[metro] = result.errors
            for e in result.errors:
                print(f"    FAIL: {e}")
        else:
            print("    OK")

    print("== lodes_panel checks: Phase 2 stub (plan Task 12 fills them)")
    print("== acs_commute_2019 checks: Phase 2 stub (plan Task 12 fills them)")
    if args.accept_access_drift:
        print("    NOTE: --accept-access-drift applies to the Phase 2 LODES access check; no-op today")

    if failures:
        print(f"\nPANEL GATE FAILED for {sorted(failures)}")
        return 1
    print("\nPANEL GATE PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
