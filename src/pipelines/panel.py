"""RQ4 panel pipeline: build_panel_flow + panel tasks (separate from build_metro_flow).

Builds the per-metro committed panel data products for RQ4 (COVID commute-gradient
repricing). This flow is deliberately separate from build_metro_flow so the
cross-sectional 35-column build path is not modified at all. The panel's ZCTA
universe is the committed 35-column dataset itself (committed_zcta_frame) — the
analysis-usable set whose covariates RQ4 joins. Geometry (ZCTA/tract centroids
for the gravity accessibility index) comes from the shared cacheable tasks in
build.py, ID-filtered to that committed universe (committed_zcta_geometries) —
never CBSA-filtered, so out-of-dataset ZIPs cannot enter the panel.

Products (design doc §1, docs/plans/2026-07-17-rq4-zori-dynamics-design.md):
zori_panel_<metro>.csv (Phase 1), lodes_panel_<metro>.csv and
acs_commute_2019_<metro>.csv (Phase 2), each validated before write and paired
with a provenance manifest.

Dev-loop cache note (design §2): TASK_SOURCE hashes only each task WRAPPER body,
not module helpers — which is exactly why the tidy_zori extraction was cache-safe,
but also means that while iterating on tidy_zori / fetch_zori_series /
fetch_state_lodes_panel (or any panel helper) under a warm 7-day cache, stale
persisted results are served with no invalidation. When editing panel helper
code mid-development, clear .prefect_cache/ or bump _PANEL_CACHE_SALT below —
the salt is a defaulted input of every cacheable panel task, so bumping it
changes the INPUTS component of the cache key and forces a refetch.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
import polars as pl

from prefect import flow, task

from .acs import fetch_acs_commute_zcta
from .build import _CACHE, fetch_state_zctas_task, fetch_tracts_task
from .config import DATA_FINAL, METRO_CONFIGS, ZORI_PANEL_CSV_URL
from .lodes import (
    LODES_PANEL_YEARS,
    fetch_state_lodes_panel,
    job_accessibility_by_year,
    states_for_counties,
)
from .manifest import build_panel_manifest, get_git_commit, write_manifest
from .prefect_config import NETWORK_RETRIES
from .schema import (
    validate_acs_commute_2019,
    validate_lodes_panel,
    validate_zori_panel,
)
from .zori import fetch_zori_series

# Bump to invalidate the panel tasks' warm cache while iterating on panel helper
# code (see the dev-loop cache note in the module docstring).
_PANEL_CACHE_SALT = 0

# Frozen pre-COVID commute vintage: ACS 5-year 2015-2019 (design §4 — the
# headline interaction set must not be measured post-treatment). Matches
# manifest._ACS_COMMUTE_2019_YEAR, which stamps the same vintage in provenance.
ACS_COMMUTE_2019_YEAR = 2019

logger = logging.getLogger(__name__)


# --- Cacheable network tasks (hashable inputs) ---
@task(name="fetch_zori_series", **NETWORK_RETRIES, **_CACHE)
def fetch_zori_series_task(
    url: str, zip_prefixes: tuple[str, ...], cache_salt: int = _PANEL_CACHE_SALT
):
    return fetch_zori_series(url, zip_prefixes)


@task(name="fetch_state_lodes_panel", **NETWORK_RETRIES, **_CACHE)
def fetch_state_lodes_panel_task(
    state_postal: str,
    years: tuple[int, ...],
    cache_salt: int = _PANEL_CACHE_SALT,
):
    """Per-state granularity (design §2 task table): a transient failure retries
    one state's files, not all states x years, and extending `years` refetches
    per-state rather than one all-states blob."""
    return fetch_state_lodes_panel(state_postal, years)


@task(name="fetch_acs_commute_zcta", **NETWORK_RETRIES, **_CACHE)
def fetch_acs_commute_zcta_task(
    states: tuple[str, ...], year: int, cache_salt: int = _PANEL_CACHE_SALT
):
    """B08303 at ZCTA altitude for each state FIPS in `states`, concatenated.

    Exact duplicate rows are dropped: when the endpoint rejects state-nesting,
    fetch_acs_commute_zcta falls back to the national pull, so every state's
    frame is the identical national set. Conflicting duplicates (same ZCTA,
    different values — e.g. state-part rows from a nested query) are NOT
    collapsed here; they survive to validate_acs_commute_2019's duplicate-key
    check and fail loudly for investigation.
    """
    frames = [fetch_acs_commute_zcta(state_fips, year) for state_fips in states]
    return (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(ignore_index=True)
        .sort_values("ZCTA5CE", kind="stable", ignore_index=True)
    )


def committed_zcta_frame(metro_key: str) -> pd.DataFrame:
    """ZCTA universe for a metro's panel products: the committed 35-column
    dataset's ZCTA5CE set (design coverage-table semantics).

    The panel is scoped to the analysis-usable universe — RQ4 joins every
    covariate from the committed dataset, so panel rows for ZCTAs outside it
    are unusable by construction (a geometric CBSA scope would include e.g.
    in-CBSA ZCTAs with no configured-county tract data).

    Raises
    ------
    FileNotFoundError
        If the committed dataset CSV is absent — build it first.
    """
    csv = DATA_FINAL / f"final_zcta_dataset_{metro_key}.csv"
    if not csv.exists():
        raise FileNotFoundError(
            f"{csv.name} is required to scope the {metro_key} panel; "
            "build the cross-sectional dataset first"
        )
    frame = pd.read_csv(csv, usecols=["ZCTA5CE"], dtype={"ZCTA5CE": str})
    frame["ZCTA5CE"] = frame["ZCTA5CE"].str.zfill(5)
    return frame


def committed_zcta_geometries(zctas_all, zctas_universe: pd.DataFrame):
    """ID-filter the prefix-pulled ZCTA geometries to the committed universe.

    The filter is by ZCTA5CE membership (never geometric CBSA containment), so
    the panel's ZCTA set stays exactly the committed dataset's set while the
    geometries feed the gravity accessibility centroids.

    Raises
    ------
    ValueError
        If any committed ZCTA has no geometry in the prefix pull — silently
        dropping it would shrink the panel grid without a trace.
    """
    zctas_all = zctas_all.copy()
    zctas_all["ZCTA5CE"] = zctas_all["ZCTA5CE"].astype(str).str.zfill(5)
    committed = set(zctas_universe["ZCTA5CE"].astype(str))
    out = zctas_all[zctas_all["ZCTA5CE"].isin(committed)].reset_index(drop=True)
    missing = sorted(committed - set(out["ZCTA5CE"]))
    if missing:
        raise ValueError(
            f"{len(missing)} committed ZCTAs have no geometry in the prefix pull "
            f"(first 10: {missing[:10]})"
        )
    return out


# --- Plain CPU tasks ---
@task(name="zori_panel")
def zori_panel_task(zori_long: pd.DataFrame, zctas_in_metro) -> pd.DataFrame:
    """[ZCTA5CE, period, zori] monthly panel for the metro's ZCTA set.

    Renames zip -> ZCTA5CE, inner-filters to the metro ZCTA set (ZIPs matching
    the prefix pull but outside the committed dataset are dropped), and
    stable-sorts by (ZCTA5CE, period) for deterministic committed bytes
    (issue #6 convention).
    """
    panel = zori_long.rename(columns={"zip": "ZCTA5CE"})
    metro_zctas = set(zctas_in_metro["ZCTA5CE"].astype(str))
    panel = panel[panel["ZCTA5CE"].isin(metro_zctas)]
    panel = panel.sort_values(["ZCTA5CE", "period"], kind="stable", ignore_index=True)
    return panel[["ZCTA5CE", "period", "zori"]]


@task(name="lodes_panel")
def lodes_panel_task(state_frames, zctas_in_metro, tracts, utm_zone: int) -> pd.DataFrame:
    """[ZCTA5CE, year, job_count, job_accessibility] on the full ZCTA x year grid.

    Concats the per-state [year, zcta, trct, jobs] frames (a pair belongs to
    exactly one state, so the re-aggregation is defensive), computes per-year
    ZCTA job counts, and 0-fills job_count ONLY for metro ZCTAs absent from a
    successfully fetched WAC year (absence = zero jobs, matching
    employment_features_task; a missing state-year already raised upstream —
    design §2). job_accessibility comes from job_accessibility_by_year on the
    same frame. Stable-sorted by (ZCTA5CE, year) for deterministic committed
    bytes (issue #6 convention).

    Both grid merges validate one_to_one, so a duplicated metro ZCTA raises
    MergeError loudly instead of silently multiplying or collapsing rows.
    """
    panel = (
        pd.concat(state_frames, ignore_index=True)
        .groupby(["year", "zcta", "trct"], as_index=False)["jobs"]
        .sum()
    )
    years = sorted(int(y) for y in panel["year"].unique())

    counts = panel.groupby(["year", "zcta"], as_index=False)["jobs"].sum()
    counts["ZCTA5CE"] = counts["zcta"].astype(str).str.zfill(5)
    counts = counts.rename(columns={"jobs": "job_count"})[
        ["ZCTA5CE", "year", "job_count"]
    ]

    zcta_ids = sorted(set(zctas_in_metro["ZCTA5CE"].astype(str).str.zfill(5)))
    grid = pd.DataFrame(
        [(zcta, year) for zcta in zcta_ids for year in years],
        columns=["ZCTA5CE", "year"],
    )

    access = job_accessibility_by_year(zctas_in_metro, tracts, panel, utm_zone)

    out = (
        grid.merge(counts, on=["ZCTA5CE", "year"], how="left", validate="one_to_one")
        .merge(access, on=["ZCTA5CE", "year"], how="left", validate="one_to_one")
    )
    out["job_count"] = out["job_count"].fillna(0).astype("int64")
    out["year"] = out["year"].astype("int64")
    return out.sort_values(["ZCTA5CE", "year"], kind="stable", ignore_index=True)


@task(name="acs_commute_2019")
def acs_commute_2019_task(acs_df: pd.DataFrame, zctas_in_metro) -> pd.DataFrame:
    """[ZCTA5CE, commute_min_proxy_2019, ttw_total_2019] for the metro ZCTA set.

    Inner-filters the (possibly national) ZCTA-altitude ACS frame to the
    committed metro set, renames to the frozen-vintage column names, and
    stable-sorts by ZCTA5CE.
    """
    metro_zctas = set(zctas_in_metro["ZCTA5CE"].astype(str))
    return (
        acs_df[acs_df["ZCTA5CE"].isin(metro_zctas)]
        .rename(
            columns={
                "commute_min_proxy": "commute_min_proxy_2019",
                "ttw_total": "ttw_total_2019",
            }
        )[["ZCTA5CE", "commute_min_proxy_2019", "ttw_total_2019"]]
        .sort_values("ZCTA5CE", kind="stable", ignore_index=True)
    )


def _pl_frame(df: pd.DataFrame) -> pl.DataFrame:
    """Column-wise pandas -> polars conversion for the schema validators
    (pl.from_pandas needs pyarrow; list round-trip does not)."""
    return pl.DataFrame({col: df[col].tolist() for col in df.columns})


@flow(name="build-panel", log_prints=True)
def build_panel_flow(metro_key: str = "phoenix") -> str:
    """Build the RQ4 panel data products for one metro.

    1. Resolves the metro ZCTA universe from the committed 35-column dataset
       (committed_zcta_frame — ID set, never geometric CBSA filtering).
    2. ZORI half: fetches the full monthly non-SA series for the metro's zip
       prefixes, filters/sorts into zori_panel_<metro>.csv.
    3. LODES half: per-state multi-year WAC fetches (submitted as futures —
       Prefect's default ThreadPoolTaskRunner runs them concurrently), ZCTA and
       tract geometries from the shared build.py tasks (warm cache after a
       dataset build) ID-filtered to the committed universe, then the full
       ZCTA x year grid with the gravity accessibility index into
       lodes_panel_<metro>.csv.
    4. ACS half: B08303 at ZCTA altitude for the frozen 2019 pre-COVID vintage
       into acs_commute_2019_<metro>.csv.

    Every product is validated against its schema validator before write
    (raises on any error — an invalid panel never lands) and paired with a
    provenance manifest (design §3).

    Returns the zori panel CSV path as a string (the flow's primary Phase-1
    contract, unchanged for run_pipeline.py).
    """
    metro_config = METRO_CONFIGS[metro_key]
    METRO_NAME = metro_config["name"]
    ZIP_PREFIXES = metro_config["zip_prefixes"]
    COUNTIES = metro_config["counties"]
    UTM_ZONE = metro_config["utm_zone"]
    ZORI_PANEL_OUT = DATA_FINAL / f"zori_panel_{metro_key}.csv"
    LODES_PANEL_OUT = DATA_FINAL / f"lodes_panel_{metro_key}.csv"
    ACS_COMMUTE_OUT = DATA_FINAL / f"acs_commute_2019_{metro_key}.csv"

    logger.info("=" * 60)
    logger.info(f"Building panel data products for: {METRO_NAME}")
    logger.info("=" * 60)

    ts = datetime.now(timezone.utc).isoformat()
    git_commit = get_git_commit()
    DATA_FINAL.mkdir(parents=True, exist_ok=True)

    # Step 1: metro ZCTA set = the committed 35-column dataset's universe
    # (design coverage-table semantics)
    logger.info("STEP 1: Resolving the metro ZCTA set from the committed dataset...")
    zctas_universe = committed_zcta_frame(metro_key)
    logger.info(f"{len(zctas_universe)} ZCTAs in the committed dataset")

    # Step 2: full monthly ZORI series (non-SA vintage; design §4 "Index choice")
    logger.info("STEP 2: Fetching the monthly ZORI series...")
    zori_long = fetch_zori_series_task(ZORI_PANEL_CSV_URL, tuple(ZIP_PREFIXES))
    logger.info(f"Fetched {len(zori_long)} ZIP-month rows for prefixes {ZIP_PREFIXES}")

    # Step 3: zori panel -> validate -> write
    zori_panel = zori_panel_task(zori_long, zctas_universe)
    errors = validate_zori_panel(_pl_frame(zori_panel))
    if errors:
        raise ValueError(f"zori_panel_{metro_key} schema violations: " + "; ".join(errors))

    zori_panel.to_csv(ZORI_PANEL_OUT, index=False)

    # Step 4: zori provenance manifest (vintage-parameterized; design §3
    # Manifests). The flow stamps its own run time as pull_timestamp_utc: a
    # warm cache may serve an earlier fetch, but committed builds run against
    # a same-day pull (Task 7 procedure), so run time ~= pull vintage.
    manifest = build_panel_manifest(
        metro_key,
        ZORI_PANEL_OUT,
        "zori_panel",
        git_commit=git_commit,
        timestamp_utc=ts,
        extra={"pull_timestamp_utc": ts},
    )
    manifest_path = DATA_FINAL / f"{metro_key}.zori_panel.manifest.json"
    write_manifest(manifest, manifest_path)
    logger.info(f"Wrote manifest {manifest_path.name}")

    # Step 5: geometries for the gravity index — shared cacheable tasks from
    # build.py (same inputs as build_metro_flow, so a panel build after a
    # dataset build hits cache), then ID-filter to the committed universe.
    logger.info("STEP 5: Fetching ZCTA/tract geometries for accessibility...")
    zctas_all = fetch_state_zctas_task(ZIP_PREFIXES)
    tracts = fetch_tracts_task(COUNTIES)
    zctas_geo = committed_zcta_geometries(zctas_all, zctas_universe)
    logger.info(f"{len(zctas_geo)} committed ZCTAs with geometry, {len(tracts)} tracts")

    # Step 6: per-state multi-year LODES fetches. Submitted as futures so the
    # default ThreadPoolTaskRunner runs the states concurrently; a transient
    # failure retries one state, and a 404 on any state-year propagates
    # (loud failure, never zero-fill — design §2).
    states = states_for_counties(COUNTIES)
    logger.info(
        f"STEP 6: Fetching LODES WAC panels for states {states}, "
        f"years {LODES_PANEL_YEARS[0]}-{LODES_PANEL_YEARS[-1]}..."
    )
    lodes_futures = [
        fetch_state_lodes_panel_task.submit(state, LODES_PANEL_YEARS)
        for state in states
    ]
    state_frames = [future.result() for future in lodes_futures]

    # Step 7: lodes panel -> validate -> write (+ years-parameterized manifest)
    lodes_panel = lodes_panel_task(state_frames, zctas_geo, tracts, UTM_ZONE)
    errors = validate_lodes_panel(_pl_frame(lodes_panel))
    if errors:
        raise ValueError(
            f"lodes_panel_{metro_key} schema violations: " + "; ".join(errors)
        )

    lodes_panel.to_csv(LODES_PANEL_OUT, index=False)
    manifest = build_panel_manifest(
        metro_key,
        LODES_PANEL_OUT,
        "lodes_panel",
        git_commit=git_commit,
        timestamp_utc=ts,
        extra={"years": [int(year) for year in LODES_PANEL_YEARS]},
    )
    manifest_path = DATA_FINAL / f"{metro_key}.lodes_panel.manifest.json"
    write_manifest(manifest, manifest_path)
    logger.info(
        f"Wrote {len(lodes_panel)} lodes panel rows and manifest {manifest_path.name}"
    )

    # Step 8: frozen pre-COVID ACS commute vintage -> validate -> write
    acs_states = tuple(sorted({state for state, _ in COUNTIES}))
    logger.info(
        f"STEP 8: Fetching ACS {ACS_COMMUTE_2019_YEAR} B08303 at ZCTA altitude "
        f"for state FIPS {acs_states}..."
    )
    acs_zcta_df = fetch_acs_commute_zcta_task(acs_states, ACS_COMMUTE_2019_YEAR)
    acs_commute = acs_commute_2019_task(acs_zcta_df, zctas_universe)
    errors = validate_acs_commute_2019(_pl_frame(acs_commute))
    if errors:
        raise ValueError(
            f"acs_commute_2019_{metro_key} schema violations: " + "; ".join(errors)
        )

    acs_commute.to_csv(ACS_COMMUTE_OUT, index=False)
    manifest = build_panel_manifest(
        metro_key,
        ACS_COMMUTE_OUT,
        "acs_commute_2019",
        git_commit=git_commit,
        timestamp_utc=ts,
        extra={},
    )
    manifest_path = DATA_FINAL / f"{metro_key}.acs_commute_2019.manifest.json"
    write_manifest(manifest, manifest_path)
    logger.info(
        f"Wrote {len(acs_commute)} ACS commute rows and manifest {manifest_path.name}"
    )

    logger.info("=" * 60)
    logger.info(
        f"SUCCESS: {ZORI_PANEL_OUT.name} ({len(zori_panel)} rows), "
        f"{LODES_PANEL_OUT.name} ({len(lodes_panel)} rows), "
        f"{ACS_COMMUTE_OUT.name} ({len(acs_commute)} rows)"
    )
    logger.info("=" * 60)

    return str(ZORI_PANEL_OUT)
