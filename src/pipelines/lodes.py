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

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

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


def zcta_job_counts(lodes_df: pd.DataFrame) -> pd.DataFrame:
    """Total jobs per ZCTA: [ZCTA5CE (str5), job_count]."""
    out = lodes_df.groupby("zcta", as_index=False)["jobs"].sum()
    out["ZCTA5CE"] = out["zcta"].astype(str).str.zfill(5)
    return out[["ZCTA5CE", "jobs"]].rename(columns={"jobs": "job_count"})


def distance_to_cbd_km(
    zctas_gdf: gpd.GeoDataFrame,
    cbd_points: list[tuple[float, float]],
    utm_zone: int,
) -> pd.DataFrame:
    """Euclidean km from each ZCTA centroid to the nearest CBD point.

    cbd_points are (lat, lon) tuples (human/map order); min over points supports
    dual-CBD metros (DFW). Distances computed in the metro's UTM CRS.
    """
    zctas = zctas_gdf.to_crs(utm_zone)
    centroids = zctas.geometry.centroid
    cbd_series = gpd.GeoSeries(
        [Point(lon, lat) for lat, lon in cbd_points], crs=4326
    ).to_crs(utm_zone)
    per_point = np.stack(
        [centroids.distance(pt).to_numpy() for pt in cbd_series], axis=1
    )
    return pd.DataFrame({
        "ZCTA5CE": zctas["ZCTA5CE"].astype(str).str.zfill(5),
        "distance_to_cbd_km": per_point.min(axis=1) / 1000.0,
    })


def job_accessibility(
    zctas_gdf: gpd.GeoDataFrame,
    tracts_gdf: gpd.GeoDataFrame,
    lodes_df: pd.DataFrame,
    utm_zone: int,
    decay_km: float = GRAVITY_DECAY_KM,
) -> pd.DataFrame:
    """Hansen-type gravity index: A_i = sum_j jobs_j * exp(-d_ij / decay_km).

    j ranges over the metro's census tracts (jobs summed from the LODES frame);
    d_ij is UTM Euclidean distance between ZCTA centroid i and tract centroid j.
    Tract altitude keeps the distance matrix small and further averages LODES
    block noise. Jobs outside the metro's counties are not counted (documented
    limitation for edge ZCTAs — consistent with the ACS county frame).
    """
    tract_jobs = lodes_df.groupby("trct", as_index=False)["jobs"].sum()
    tracts = tracts_gdf.to_crs(utm_zone).copy()
    tracts["trct"] = tracts["GEOID"].astype(str).str.zfill(11)
    tracts = tracts.merge(tract_jobs, on="trct", how="inner")

    zctas = zctas_gdf.to_crs(utm_zone)
    zcta_ids = zctas["ZCTA5CE"].astype(str).str.zfill(5)

    if tracts.empty:
        logger.warning("job_accessibility: no tracts matched LODES jobs; returning 0s")
        return pd.DataFrame({
            "ZCTA5CE": zcta_ids,
            "job_accessibility": np.zeros(len(zctas)),
        })

    tract_cent = tracts.geometry.centroid
    tract_xy = np.column_stack([tract_cent.x.to_numpy(), tract_cent.y.to_numpy()])
    jobs = tracts["jobs"].to_numpy(dtype=float)

    zcta_cent = zctas.geometry.centroid
    zcta_xy = np.column_stack([zcta_cent.x.to_numpy(), zcta_cent.y.to_numpy()])

    # Pairwise (n_zcta, n_tract) distances in km
    d_km = np.sqrt(
        ((zcta_xy[:, None, :] - tract_xy[None, :, :]) ** 2).sum(axis=2)
    ) / 1000.0
    access = (jobs[None, :] * np.exp(-d_km / decay_km)).sum(axis=1)

    return pd.DataFrame({"ZCTA5CE": zcta_ids, "job_accessibility": access})
