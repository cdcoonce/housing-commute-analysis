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

# RQ4 annual panel window: 2015 matches the ZORI window start; 2023 is the
# newest published LODES8 year (extend when 2024 drops — the panel gate is
# append-only). The single-year LODES_YEAR cross-sectional path is untouched.
LODES_PANEL_YEARS: tuple[int, ...] = tuple(range(2015, 2024))

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


def fetch_state_xwalk(state_postal: str) -> pd.DataFrame:
    """One state's LODES block→geography crosswalk, filtered to real ZCTAs.

    Returns [tabblk2020, zcta, trct]. Blocks with a blank or "99999" crosswalk
    zcta (unpopulated water/park blocks) are dropped; they carry ~0 jobs.

    Uncached helper (never a Prefect-persisted result): the raw crosswalk is
    2.7-11.4 MB gz (verified 2026-07-17) and retaining it would violate the
    cache-size discipline. Callers join it and keep only slim aggregates.
    """
    xwalk = http_csv_to_df(
        xwalk_url(state_postal),
        compression="gzip",
        dtype={"tabblk2020": str, "zcta": str, "trct": str},
        usecols=["tabblk2020", "zcta", "trct"],
    )
    xwalk = xwalk[xwalk["zcta"].str.fullmatch(r"\d{5}", na=False)]
    return xwalk[xwalk["zcta"] != "99999"]


def _wac_zcta_tract_jobs(
    state_postal: str, year: int, xwalk: pd.DataFrame
) -> pd.DataFrame:
    """One state-year WAC joined to a pre-fetched crosswalk: [zcta, trct, jobs].

    HTTP errors (including a 404 on an unpublished state-year) propagate —
    a missing state-year is a loud failure, never a silent zero-fill.
    """
    wac = http_csv_to_df(
        wac_url(state_postal, year),
        compression="gzip",
        dtype={"w_geocode": str},
        usecols=["w_geocode", "C000"],
    )
    merged = wac.merge(xwalk, left_on="w_geocode", right_on="tabblk2020", how="inner")
    return (
        merged.groupby(["zcta", "trct"], as_index=False)["C000"]
        .sum()
        .rename(columns={"C000": "jobs"})
    )


def fetch_state_jobs(state_postal: str, year: int = LODES_YEAR) -> pd.DataFrame:
    """One state's block-level jobs joined to ZCTA + tract via the LODES crosswalk.

    Returns the slim frame [zcta, trct, jobs] aggregated to (zcta, trct) pairs.
    Raw block rows and the (2.7-11.4 MB gz, verified 2026-07-17) crosswalk are
    NOT retained — this keeps the Prefect-persisted cache result small.
    """
    out = _wac_zcta_tract_jobs(state_postal, year, fetch_state_xwalk(state_postal))
    logger.info(
        "LODES %s %s: %d (zcta, tract) pairs, %d jobs",
        state_postal, year, len(out), int(out["jobs"].sum()),
    )
    return out


def fetch_state_lodes_panel(
    state_postal: str, years: tuple[int, ...] = LODES_PANEL_YEARS
) -> pd.DataFrame:
    """One state's (zcta, tract) job counts for every year in `years`.

    Downloads the state crosswalk ONCE, then joins each year's WAC file
    against it. An HTTP error on any single year **propagates** — a missing
    state-year must abort the panel build, never zero-fill (design §2).

    Returns [year, zcta, trct, jobs], aggregated per (year, zcta, trct) and
    stable-sorted (issue #6 ordering convention).
    """
    xwalk = fetch_state_xwalk(state_postal)
    frames = []
    for year in years:
        year_frame = _wac_zcta_tract_jobs(state_postal, year, xwalk)
        year_frame.insert(0, "year", int(year))
        frames.append(year_frame)
    out = (
        pd.concat(frames, ignore_index=True)
        .groupby(["year", "zcta", "trct"], as_index=False)["jobs"]
        .sum()
        .sort_values(["year", "zcta", "trct"], kind="stable", ignore_index=True)
    )
    logger.info(
        "LODES panel %s %s-%s: %d (year, zcta, tract) rows, %d job-years",
        state_postal, min(years), max(years), len(out), int(out["jobs"].sum()),
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
    # Stable-sort by tract GEOID (issue #6): the gravity sum below reduces over
    # the tract axis in this frame's row order, and TIGERweb feature order is
    # not stable — sorting pins the reduction order so the index is
    # byte-identical under any permutation of the input rows.
    tracts = tracts.merge(tract_jobs, on="trct", how="inner").sort_values(
        "trct", kind="stable", ignore_index=True
    )

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


def job_accessibility_by_year(
    zctas_gdf: gpd.GeoDataFrame,
    tracts_gdf: gpd.GeoDataFrame,
    lodes_panel_df: pd.DataFrame,
    utm_zone: int,
    decay_km: float = GRAVITY_DECAY_KM,
) -> pd.DataFrame:
    """Gravity job-accessibility per (ZCTA, year), vectorized across years.

    The (n_zcta, n_tract) decay matrix exp(-D/decay_km) is computed ONCE and
    multiplied against an (n_tract, n_years) jobs matrix built on the UNION
    tract axis: a tract with jobs in only some years is 0-filled in the others
    (never carried forward). Tract rows are stable-sorted by `trct` before the
    reduction (issue #6 order-invariance convention).

    Agreement with the single-year `job_accessibility` for a shared year holds
    at np.allclose, NOT byte-equality: the matmul's pairwise-summation grouping
    differs from the single-year broadcast-and-sum (design §2).

    Returns [ZCTA5CE, year, job_accessibility] — ZCTAs in zctas_gdf row order
    (matching `job_accessibility`), years ascending within each ZCTA.
    """
    tract_year_jobs = (
        lodes_panel_df.groupby(["trct", "year"], as_index=False)["jobs"]
        .sum()
        .pivot(index="trct", columns="year", values="jobs")
        .fillna(0.0)
        .sort_index(kind="stable")
        .sort_index(axis=1)
    )
    years = [int(y) for y in tract_year_jobs.columns]

    tracts = tracts_gdf.to_crs(utm_zone).copy()
    tracts["trct"] = tracts["GEOID"].astype(str).str.zfill(11)
    tracts = tracts.merge(
        tract_year_jobs.reset_index(), on="trct", how="inner"
    ).sort_values("trct", kind="stable", ignore_index=True)

    zctas = zctas_gdf.to_crs(utm_zone)
    zcta_ids = zctas["ZCTA5CE"].astype(str).str.zfill(5)

    if tracts.empty:
        logger.warning(
            "job_accessibility_by_year: no tracts matched LODES jobs; returning 0s"
        )
        return pd.DataFrame({
            "ZCTA5CE": np.repeat(zcta_ids.to_numpy(), len(years)),
            "year": np.tile(np.asarray(years, dtype=int), len(zctas)),
            "job_accessibility": np.zeros(len(zctas) * len(years)),
        })

    tract_cent = tracts.geometry.centroid
    tract_xy = np.column_stack([tract_cent.x.to_numpy(), tract_cent.y.to_numpy()])
    jobs_by_year = tracts[years].to_numpy(dtype=float)  # (n_tract, n_years)

    zcta_cent = zctas.geometry.centroid
    zcta_xy = np.column_stack([zcta_cent.x.to_numpy(), zcta_cent.y.to_numpy()])

    # Pairwise (n_zcta, n_tract) distances in km — computed once for all years
    d_km = np.sqrt(
        ((zcta_xy[:, None, :] - tract_xy[None, :, :]) ** 2).sum(axis=2)
    ) / 1000.0
    access = np.exp(-d_km / decay_km) @ jobs_by_year  # (n_zcta, n_years)

    return pd.DataFrame({
        "ZCTA5CE": np.repeat(zcta_ids.to_numpy(), len(years)),
        "year": np.tile(np.asarray(years, dtype=int), len(zctas)),
        "job_accessibility": access.ravel(),
    })
