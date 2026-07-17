"""RQ4 panel pipeline: build_panel_flow + panel tasks (separate from build_metro_flow).

Builds the per-metro committed panel data products for RQ4 (COVID commute-gradient
repricing). This flow is deliberately separate from build_metro_flow so the
cross-sectional 35-column build path is not modified at all; the shared cacheable
geo tasks (fetch_cbsa_boundary_task, fetch_state_zctas_task, filter_zctas_task)
are imported from build.py — Prefect's INPUTS + TASK_SOURCE cache is flow-agnostic,
so a panel build after a dataset build hits cache on all shared fetches.

Phase 1 covers the ZORI half (zori_panel_<metro>.csv); the LODES/ACS halves land
in Phase 2 (design doc §2, docs/plans/2026-07-17-rq4-zori-dynamics-design.md).

Dev-loop cache note (design §2): TASK_SOURCE hashes only each task WRAPPER body,
not module helpers — which is exactly why the tidy_zori extraction was cache-safe,
but also means that while iterating on tidy_zori / fetch_zori_series (or any
panel helper) under a warm 7-day cache, stale persisted results are served with
no invalidation. When editing panel helper code mid-development, clear
.prefect_cache/ or bump _PANEL_CACHE_SALT below — the salt is a defaulted input
of every cacheable panel task, so bumping it changes the INPUTS component of the
cache key and forces a refetch.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
import polars as pl

from prefect import flow, task

from .build import (
    _CACHE,
    fetch_cbsa_boundary_task,
    fetch_state_zctas_task,
    filter_zctas_task,
)
from .config import DATA_FINAL, METRO_CONFIGS, ZORI_PANEL_CSV_URL
from .manifest import build_panel_manifest, get_git_commit, write_manifest
from .prefect_config import NETWORK_RETRIES
from .schema import validate_zori_panel
from .zori import fetch_zori_series

# Bump to invalidate the panel tasks' warm cache while iterating on panel helper
# code (see the dev-loop cache note in the module docstring).
_PANEL_CACHE_SALT = 0

logger = logging.getLogger(__name__)


# --- Cacheable network tasks (hashable inputs) ---
@task(name="fetch_zori_series", **NETWORK_RETRIES, **_CACHE)
def fetch_zori_series_task(
    url: str, zip_prefixes: tuple[str, ...], cache_salt: int = _PANEL_CACHE_SALT
):
    return fetch_zori_series(url, zip_prefixes)


# --- Plain CPU tasks ---
@task(name="zori_panel")
def zori_panel_task(zori_long: pd.DataFrame, zctas_in_metro) -> pd.DataFrame:
    """[ZCTA5CE, period, zori] monthly panel for the metro's ZCTA set.

    Renames zip -> ZCTA5CE, inner-filters to the metro ZCTA set (ZIPs matching
    the prefix pull but outside the CBSA are dropped), and stable-sorts by
    (ZCTA5CE, period) for deterministic committed bytes (issue #6 convention).
    """
    panel = zori_long.rename(columns={"zip": "ZCTA5CE"})
    metro_zctas = set(zctas_in_metro["ZCTA5CE"].astype(str))
    panel = panel[panel["ZCTA5CE"].isin(metro_zctas)]
    panel = panel.sort_values(["ZCTA5CE", "period"], kind="stable", ignore_index=True)
    return panel[["ZCTA5CE", "period", "zori"]]


@flow(name="build-panel", log_prints=True)
def build_panel_flow(metro_key: str = "phoenix") -> str:
    """Build the RQ4 panel data products for one metro (Phase 1: ZORI half).

    1. Fetches CBSA boundary + state ZCTAs and filters to the metro (shared
       cacheable tasks from build.py — cache hits after a dataset build).
    2. Fetches the full monthly non-SA ZORI series for the metro's zip prefixes.
    3. Filters/renames/sorts into the zori panel, validates it against
       validate_zori_panel (raises on any error — an invalid panel never lands),
       then writes data/final/zori_panel_<metro>.csv.

    Returns the output CSV path as a string.
    """
    metro_config = METRO_CONFIGS[metro_key]
    CBSA_CODE = metro_config["cbsa_code"]
    METRO_NAME = metro_config["name"]
    UTM_ZONE = metro_config["utm_zone"]
    ZIP_PREFIXES = metro_config["zip_prefixes"]
    ZORI_PANEL_OUT = DATA_FINAL / f"zori_panel_{metro_key}.csv"

    logger.info("=" * 60)
    logger.info(f"Building panel data products for: {METRO_NAME}")
    logger.info("=" * 60)

    # Step 1: metro ZCTA set (shared cacheable geo tasks)
    logger.info("STEP 1: Resolving the metro ZCTA set...")
    cbsa_boundary = fetch_cbsa_boundary_task(CBSA_CODE)
    zctas_all = fetch_state_zctas_task(ZIP_PREFIXES)
    zctas_in_metro = filter_zctas_task(zctas_all, cbsa_boundary, UTM_ZONE)
    logger.info(f"{len(zctas_in_metro)} ZCTAs in metro")

    # Step 2: full monthly ZORI series (non-SA vintage; design §4 "Index choice")
    logger.info("STEP 2: Fetching the monthly ZORI series...")
    zori_long = fetch_zori_series_task(ZORI_PANEL_CSV_URL, tuple(ZIP_PREFIXES))
    logger.info(f"Fetched {len(zori_long)} ZIP-month rows for prefixes {ZIP_PREFIXES}")

    # Step 3: metro panel -> validate -> write
    zori_panel = zori_panel_task(zori_long, zctas_in_metro)
    errors = validate_zori_panel(
        pl.DataFrame(
            {
                "ZCTA5CE": zori_panel["ZCTA5CE"].tolist(),
                "period": zori_panel["period"].tolist(),
                "zori": zori_panel["zori"].tolist(),
            }
        )
    )
    if errors:
        raise ValueError(f"zori_panel_{metro_key} schema violations: " + "; ".join(errors))

    ZORI_PANEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    zori_panel.to_csv(ZORI_PANEL_OUT, index=False)

    # Step 4: provenance manifest (vintage-parameterized; design §3 Manifests).
    # The flow stamps its own run time as pull_timestamp_utc: a warm cache may
    # serve an earlier fetch, but committed builds run against a same-day pull
    # (Task 7 procedure), so run time ~= pull vintage.
    ts = datetime.now(timezone.utc).isoformat()
    manifest = build_panel_manifest(
        metro_key,
        ZORI_PANEL_OUT,
        "zori_panel",
        git_commit=get_git_commit(),
        timestamp_utc=ts,
        extra={"pull_timestamp_utc": ts},
    )
    manifest_path = DATA_FINAL / f"{metro_key}.zori_panel.manifest.json"
    write_manifest(manifest, manifest_path)
    logger.info(f"Wrote manifest {manifest_path.name}")

    logger.info("=" * 60)
    logger.info(f"SUCCESS: Wrote {len(zori_panel)} panel rows to {ZORI_PANEL_OUT.name}")
    logger.info("=" * 60)

    return str(ZORI_PANEL_OUT)
