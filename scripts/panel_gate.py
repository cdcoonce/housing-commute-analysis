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

LODES panel — append-only with a float-honest comparison (design §3): published
LODES8 files are immutable, so on existing (ZCTA5CE, year) cells `job_count`
(integer sums of immutable inputs) must be BYTE-identical (string compare under
dtype=str) — a change means an upstream reissue and must be investigated, NO
escape hatch. `job_accessibility` is a derived float whose bits depend on
BLAS/numpy pairwise summation and on the TIGERweb geometry vintage, so it is
compared at FLOAT_NOISE_RTOL with the max relative delta always reported;
--accept-access-drift (reviewed-human-only) waives exactly that check for the
geometry-vintage case. New years may appear at the TAIL only; a removed year or
a removed (ZCTA5CE, year) cell fails.

ACS 2019 — frozen vintage (design §3): the 2015-2019 release is final, so
`ttw_total_2019` must be byte-identical, `commute_min_proxy_2019` within
FLOAT_NOISE_RTOL, and the ZCTA set unchanged in both directions. No escape
hatch — a Census API vintage does not revise; a change means our query or
midpoints changed.

LODES new-data sanity (design §3): min(job_accessibility) > 0 (protects the §4
log transform — a zero would be a high-leverage -inf) and, per year, Spearman
rho(job_accessibility, distance_to_cbd_km) < 0 against the metro's 35-column
final_zcta_dataset (access falls with distance, every year).

Reads with dtype=str; numeric comparisons via pd.to_numeric (design §1),
exactly like rebuild_gate.py:127-128.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr

ZCTA_CHURN_MAX = 0.05
LOST_CELLS_MAX = 0.01
REVISED_CELLS_MAX = 0.01
REVISION_TOL = 0.05
REVISION_MAX_SINGLE = 0.25
# Same value as rebuild_gate.py:47-49 — last-ULP float noise, not a revision.
FLOAT_NOISE_RTOL = 1e-12

ZORI_PANEL_COLUMNS = ["ZCTA5CE", "period", "zori"]
LODES_PANEL_COLUMNS = ["ZCTA5CE", "year", "job_count", "job_accessibility"]
ACS_COMMUTE_2019_COLUMNS = ["ZCTA5CE", "commute_min_proxy_2019", "ttw_total_2019"]
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


def check_lodes_panel(
    baseline: pd.DataFrame,
    new: pd.DataFrame,
    accept_access_drift: bool = False,
) -> GateResult:
    """Gate one metro's regenerated LODES panel against its committed baseline.

    Append-only (design §3): every baseline (ZCTA5CE, year) cell must survive
    with byte-identical `job_count` (string compare under dtype=str; NO escape
    hatch — a change is an upstream reissue to investigate) and
    `job_accessibility` within FLOAT_NOISE_RTOL (max relative delta always
    reported in ``revision_report``; ``accept_access_drift`` — reviewed-human-
    only — waives exactly that check for the geometry-vintage case). New years
    may append at the tail only.
    """
    if list(new.columns) != LODES_PANEL_COLUMNS:
        return GateResult(
            ok=False,
            errors=[f"schema: columns must be exactly {LODES_PANEL_COLUMNS}, got {list(new.columns)}"],
            revision_report={},
        )

    errors: list[str] = []

    base_years = set(pd.to_numeric(baseline["year"], errors="coerce"))
    new_years = set(pd.to_numeric(new["year"], errors="coerce"))
    removed_years = sorted(base_years - new_years)
    if removed_years:
        errors.append(
            f"append-only: {len(removed_years)} baseline years removed from new panel: "
            f"{[int(y) for y in removed_years]}"
        )
    tail = max(base_years)
    before_tail = sorted(y for y in new_years - base_years if y <= tail)
    if before_tail:
        errors.append(
            f"append-only: new years {[int(y) for y in before_tail]} do not append at the "
            f"tail (baseline max year {int(tail)}) — history rewrite, not an append"
        )

    # Removed cells within years that still exist (whole-year loss is already
    # reported above; double-reporting every cell of it would only add noise).
    base_cells = set(zip(baseline["ZCTA5CE"].astype(str), pd.to_numeric(baseline["year"], errors="coerce")))
    new_cells = set(zip(new["ZCTA5CE"].astype(str), pd.to_numeric(new["year"], errors="coerce")))
    missing = sorted((z, int(y)) for z, y in base_cells - new_cells if y in new_years)
    if missing:
        errors.append(
            f"append-only: {len(missing)} baseline (ZCTA5CE, year) cells absent from new "
            f"panel (first 10: {missing[:10]})"
        )

    merged = baseline.merge(new, on=["ZCTA5CE", "year"], suffixes=("_base", "_new"))
    n_overlap = len(merged)

    # job_count: byte-identity, no hatch.
    diff_jobs = merged["job_count_base"].astype(str) != merged["job_count_new"].astype(str)
    if diff_jobs.any():
        sample = sorted(
            zip(merged.loc[diff_jobs, "ZCTA5CE"], merged.loc[diff_jobs, "year"].astype(str))
        )[:10]
        errors.append(
            f"job_count changed on {int(diff_jobs.sum())} existing cells (upstream "
            f"reissue — investigate; NO escape hatch; first 10: {sample})"
        )

    # job_accessibility: float-honest comparison at FLOAT_NOISE_RTOL.
    base_acc = pd.to_numeric(merged["job_accessibility_base"], errors="coerce")
    new_acc = pd.to_numeric(merged["job_accessibility_new"], errors="coerce")
    if base_acc.isna().any() or new_acc.isna().any():
        errors.append(
            f"job_accessibility has {int(base_acc.isna().sum() + new_acc.isna().sum())} "
            "null/non-numeric cells on the overlap"
        )
    rel = (new_acc - base_acc).abs() / base_acc.abs()
    revision_report: dict[str, float] = {
        "n_overlap": n_overlap,
        "access_max_rel_delta": float(rel.max()) if n_overlap else 0.0,
    }
    access_errors: list[str] = []
    n_beyond = int((rel > FLOAT_NOISE_RTOL).sum())
    if n_beyond:
        access_errors.append(
            f"job_accessibility drift beyond FLOAT_NOISE_RTOL={FLOAT_NOISE_RTOL:.0e} on "
            f"{n_beyond} of {n_overlap} existing cells "
            f"(max |delta|/baseline = {revision_report['access_max_rel_delta']:.2e})"
        )

    waived: list[str] = []
    if accept_access_drift:
        for e in access_errors:
            waived.append(f"--accept-access-drift waived: {e}")
            print(f"    waived (--accept-access-drift): {e}")
    else:
        errors.extend(access_errors)

    return GateResult(ok=not errors, errors=errors, revision_report=revision_report, waived=waived)


def check_acs_commute_2019(baseline: pd.DataFrame, new: pd.DataFrame) -> GateResult:
    """Gate the regenerated frozen-vintage ACS 2019 commute file (design §3).

    The 2015-2019 release is final: `ttw_total_2019` byte-identical,
    `commute_min_proxy_2019` within FLOAT_NOISE_RTOL, ZCTA set unchanged in
    both directions. NO escape hatch — a Census API vintage does not revise;
    any larger change means our query or midpoints changed.
    """
    if list(new.columns) != ACS_COMMUTE_2019_COLUMNS:
        return GateResult(
            ok=False,
            errors=[f"schema: columns must be exactly {ACS_COMMUTE_2019_COLUMNS}, got {list(new.columns)}"],
            revision_report={},
        )

    errors: list[str] = []
    base_zctas = set(baseline["ZCTA5CE"].astype(str))
    new_zctas = set(new["ZCTA5CE"].astype(str))
    lost = sorted(base_zctas - new_zctas)
    if lost:
        errors.append(
            f"frozen vintage: {len(lost)} baseline ZCTAs absent from new file "
            f"(first 10: {lost[:10]})"
        )
    gained = sorted(new_zctas - base_zctas)
    if gained:
        errors.append(
            f"frozen vintage: {len(gained)} ZCTAs appeared that are absent from baseline "
            f"(first 10: {gained[:10]}) — query or code-match changed"
        )

    merged = baseline.merge(new, on="ZCTA5CE", suffixes=("_base", "_new"))
    n_overlap = len(merged)

    diff_ttw = merged["ttw_total_2019_base"].astype(str) != merged["ttw_total_2019_new"].astype(str)
    if diff_ttw.any():
        errors.append(
            f"ttw_total_2019 changed on {int(diff_ttw.sum())} ZCTAs "
            "(frozen vintage — NO escape hatch)"
        )

    base_proxy = pd.to_numeric(merged["commute_min_proxy_2019_base"], errors="coerce")
    new_proxy = pd.to_numeric(merged["commute_min_proxy_2019_new"], errors="coerce")
    if base_proxy.isna().any() or new_proxy.isna().any():
        errors.append(
            f"commute_min_proxy_2019 has "
            f"{int(base_proxy.isna().sum() + new_proxy.isna().sum())} null/non-numeric "
            "cells on the overlap"
        )
    rel = (new_proxy - base_proxy).abs() / base_proxy.abs()
    revision_report: dict[str, float] = {
        "n_overlap": n_overlap,
        "proxy_max_rel_delta": float(rel.max()) if n_overlap else 0.0,
    }
    n_beyond = int((rel > FLOAT_NOISE_RTOL).sum())
    if n_beyond:
        errors.append(
            f"commute_min_proxy_2019 drift beyond FLOAT_NOISE_RTOL={FLOAT_NOISE_RTOL:.0e} "
            f"on {n_beyond} of {n_overlap} ZCTAs "
            f"(max |delta|/baseline = {revision_report['proxy_max_rel_delta']:.2e}; NO escape hatch)"
        )

    return GateResult(ok=not errors, errors=errors, revision_report=revision_report)


def check_lodes_sanity(new: pd.DataFrame, cross: pd.DataFrame) -> list[str]:
    """New-data sanity for a regenerated LODES panel (design §3).

    ``cross`` is the metro's 35-column final_zcta_dataset (dtype=str is fine);
    only ZCTA5CE and distance_to_cbd_km are used. Checks:
    min(job_accessibility) > 0 (log-transform guard) and, PER YEAR, Spearman
    rho(job_accessibility, distance_to_cbd_km) < 0 — access falls with
    distance every year, not just pooled.
    """
    errors: list[str] = []
    access = pd.to_numeric(new["job_accessibility"], errors="coerce")
    n_bad = int((access <= 0).sum() + access.isna().sum())
    if n_bad:
        errors.append(
            f"sanity: job_accessibility must be > 0 (log-transform guard): "
            f"{n_bad} cells <= 0 or null (min={access.min()})"
        )

    panel = pd.DataFrame({
        "ZCTA5CE": new["ZCTA5CE"].astype(str),
        "year": pd.to_numeric(new["year"], errors="coerce"),
        "access": access,
    })
    dist = pd.DataFrame({
        "ZCTA5CE": cross["ZCTA5CE"].astype(str),
        "dist": pd.to_numeric(cross["distance_to_cbd_km"], errors="coerce"),
    })
    joined = panel.merge(dist, on="ZCTA5CE")
    for year, grp in joined.groupby("year"):
        rho = spearmanr(grp["access"], grp["dist"]).statistic
        if not rho < 0:                    # NaN rho fails too — loud on weird data
            errors.append(
                f"sanity: year {int(year)} Spearman rho(job_accessibility, "
                f"distance_to_cbd_km) = {rho:.3f}, expected < 0"
            )
    return errors


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
        help=(
            "Waive the LODES job_accessibility rtol check for the geometry-vintage "
            "case (reviewed-human-only; quote gate output in the PR)"
        ),
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
            failures[f"{metro}/zori"] = [f"regenerated panel missing: {new_csv}"]
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
            failures[f"{metro}/zori"] = result.errors
            for e in result.errors:
                print(f"    FAIL: {e}")
        else:
            print("    OK")

    lodes_baselines = sorted(baseline_dir.glob("lodes_panel_*.csv"))
    if not lodes_baselines:
        print(f"== lodes_panel checks: no baselines in {baseline_dir} (first Phase-2 build?)")
    for baseline_csv in lodes_baselines:
        metro = baseline_csv.stem.replace("lodes_panel_", "")
        print(f"== {metro} (lodes panel)")
        new_csv = FINAL_DIR / baseline_csv.name
        if not new_csv.exists():
            failures[f"{metro}/lodes"] = [f"regenerated panel missing: {new_csv}"]
            print(f"    FAIL: regenerated panel missing: {new_csv}")
            continue
        baseline = pd.read_csv(baseline_csv, dtype=str)
        new = pd.read_csv(new_csv, dtype=str)
        result = check_lodes_panel(baseline, new, accept_access_drift=args.accept_access_drift)
        report = result.revision_report
        if report:
            print(
                f"    job_accessibility on {report['n_overlap']} existing cells: "
                f"max |delta|/baseline = {report['access_max_rel_delta']:.2e} "
                f"(FLOAT_NOISE_RTOL={FLOAT_NOISE_RTOL:.0e})"
            )
        errors = list(result.errors)
        cross_csv = FINAL_DIR / f"final_zcta_dataset_{metro}.csv"
        if not cross_csv.exists():
            errors.append(f"sanity: 35-column dataset missing: {cross_csv}")
        else:
            errors.extend(check_lodes_sanity(new, pd.read_csv(cross_csv, dtype=str)))
        if errors:
            failures[f"{metro}/lodes"] = errors
            for e in errors:
                print(f"    FAIL: {e}")
        else:
            print("    OK")

    acs_baselines = sorted(baseline_dir.glob("acs_commute_2019_*.csv"))
    if not acs_baselines:
        print(f"== acs_commute_2019 checks: no baselines in {baseline_dir} (first Phase-2 build?)")
    for baseline_csv in acs_baselines:
        metro = baseline_csv.stem.replace("acs_commute_2019_", "")
        print(f"== {metro} (acs commute 2019)")
        new_csv = FINAL_DIR / baseline_csv.name
        if not new_csv.exists():
            failures[f"{metro}/acs2019"] = [f"regenerated file missing: {new_csv}"]
            print(f"    FAIL: regenerated file missing: {new_csv}")
            continue
        baseline = pd.read_csv(baseline_csv, dtype=str)
        new = pd.read_csv(new_csv, dtype=str)
        result = check_acs_commute_2019(baseline, new)
        report = result.revision_report
        if report:
            print(
                f"    commute_min_proxy_2019 on {report['n_overlap']} ZCTAs: "
                f"max |delta|/baseline = {report['proxy_max_rel_delta']:.2e} "
                f"(FLOAT_NOISE_RTOL={FLOAT_NOISE_RTOL:.0e})"
            )
        if result.errors:
            failures[f"{metro}/acs2019"] = result.errors
            for e in result.errors:
                print(f"    FAIL: {e}")
        else:
            print("    OK")

    if failures:
        print(f"\nPANEL GATE FAILED for {sorted(failures)}")
        return 1
    print("\nPANEL GATE PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
