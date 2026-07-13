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
