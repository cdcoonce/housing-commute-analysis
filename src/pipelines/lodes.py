"""LEHD LODES employment data: fetch, ZCTA/tract aggregation, derived features.

Source: LODES8 Workplace Area Characteristics (WAC) — job counts by 2020 census
block. 2020 blocks nest exactly in the 2020-vintage ZCTAs this pipeline uses,
so block→ZCTA assignment via the LODES crosswalk is exact containment (no
areal interpolation). Public domain, no auth. LODES counts UI-covered + federal
civilian jobs only (no self-employed / military / informal).

Block-level values are noise-infused for confidentiality — only ZCTA- and
tract-level sums are consumed here, where the noise washes out.
"""
from __future__ import annotations

import logging

import pandas as pd

from .utils import http_csv_to_df

logger = logging.getLogger(__name__)

# 2021 pairs with the ACS 5-Year 2017-2021 commute vintage (acs.DEFAULT_ACS_YEAR).
# LODES year = April 1 snapshot; 2021 is COVID-affected (documented in the design).
LODES_YEAR = 2021
LODES_VERSION = "LODES8"  # 2020 census blocks — do NOT use LODES7 (2010 blocks)
LODES_BASE_URL = "https://lehd.ces.census.gov/data/lodes"

# Exponential decay length (km) for the gravity job-accessibility index.
# The single sensitivity knob for job_accessibility; see design doc.
GRAVITY_DECAY_KM = 10.0

# Only the states covering the 9 configured metros. Extend when adding metros.
STATE_FIPS_TO_POSTAL = {
    "04": "az", "05": "ar", "06": "ca", "08": "co", "12": "fl", "13": "ga",
    "17": "il", "28": "ms", "47": "tn", "48": "tx", "53": "wa",
}


def wac_url(state_postal: str, year: int = LODES_YEAR) -> str:
    """WAC file URL: all-jobs (JT00), all-workers segment (S000), one state-year."""
    return (
        f"{LODES_BASE_URL}/{LODES_VERSION}/{state_postal}/wac/"
        f"{state_postal}_wac_S000_JT00_{year}.csv.gz"
    )


def xwalk_url(state_postal: str) -> str:
    """Geography crosswalk URL: maps 2020 blocks to ZCTA, tract, and more."""
    return f"{LODES_BASE_URL}/{LODES_VERSION}/{state_postal}/{state_postal}_xwalk.csv.gz"


def states_for_counties(counties: list[tuple[str, str]]) -> tuple[str, ...]:
    """Distinct postal codes for a metro's (state_fips, county_fips) list, sorted.

    Returns a tuple (hashable) so it can key a cacheable Prefect task.

    Raises
    ------
    KeyError
        If a state FIPS has no postal mapping (extend STATE_FIPS_TO_POSTAL).
    """
    fips = sorted({state for state, _ in counties})
    unmapped = [f for f in fips if f not in STATE_FIPS_TO_POSTAL]
    if unmapped:
        raise KeyError(
            f"No postal mapping for state FIPS {unmapped}; extend STATE_FIPS_TO_POSTAL"
        )
    return tuple(sorted(STATE_FIPS_TO_POSTAL[f] for f in fips))


def fetch_state_jobs(state_postal: str, year: int = LODES_YEAR) -> pd.DataFrame:
    """One state's block-level jobs joined to ZCTA + tract via the LODES crosswalk.

    Returns the slim frame [zcta, trct, jobs] aggregated to (zcta, trct) pairs.
    Raw block rows and the (large, ~10-60 MB gz) crosswalk are NOT retained —
    this keeps the Prefect-persisted cache result small.

    Blocks with a blank or "99999" crosswalk zcta (unpopulated water/park
    blocks) are dropped; they carry ~0 jobs.
    """
    wac = http_csv_to_df(
        wac_url(state_postal, year),
        compression="gzip",
        dtype={"w_geocode": str},
        usecols=["w_geocode", "C000"],
    )
    xwalk = http_csv_to_df(
        xwalk_url(state_postal),
        compression="gzip",
        dtype={"tabblk2020": str, "zcta": str, "trct": str},
        usecols=["tabblk2020", "zcta", "trct"],
    )
    xwalk = xwalk[xwalk["zcta"].str.fullmatch(r"\d{5}", na=False)]
    xwalk = xwalk[xwalk["zcta"] != "99999"]

    merged = wac.merge(xwalk, left_on="w_geocode", right_on="tabblk2020", how="inner")
    out = (
        merged.groupby(["zcta", "trct"], as_index=False)["C000"]
        .sum()
        .rename(columns={"C000": "jobs"})
    )
    logger.info(
        "LODES %s %s: %d (zcta, tract) pairs, %d jobs",
        state_postal, year, len(out), int(out["jobs"].sum()),
    )
    return out


def fetch_metro_lodes(states: tuple[str, ...], year: int = LODES_YEAR) -> pd.DataFrame:
    """All states' job frames for a metro, concatenated and re-aggregated.

    A (zcta, tract) pair belongs to exactly one state, so the re-aggregation is
    defensive only. `states` is a tuple so the wrapping Prefect task stays
    cacheable on its inputs.
    """
    frames = [fetch_state_jobs(s, year) for s in states]
    return (
        pd.concat(frames, ignore_index=True)
        .groupby(["zcta", "trct"], as_index=False)["jobs"]
        .sum()
    )
