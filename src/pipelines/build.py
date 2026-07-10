"""Main pipeline orchestration for building ZCTA-level housing dataset.

This module coordinates the entire data pipeline: fetching geographic boundaries,
retrieving census and rental data, computing spatial joins, and aggregating to
produce a final ZCTA-level dataset with housing, commute, and transit metrics.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import geopandas as gpd
import pandas as pd
import polars as pl

from .acs import compute_acs_features, fetch_acs_for_county
from .config import DATA_FINAL, METRO_CONFIGS, PROJECT_ROOT, ZORI_ZIP_CSV_URL
from .demographics import (
    aggregate_demographics_to_zcta,
    compute_demographic_percentages,
    create_income_segments,
    fetch_demographics_for_county,
)
from .osm import zcta_transit_density
from .spatial import filter_zctas_in_cbsa, tract_to_zcta_centroid_map
from .tiger import get_cbsa_polygon, get_tracts_for_counties, get_state_zctas
from .zori import fetch_zori_latest

from prefect import flow, task
from prefect.cache_policies import INPUTS, TASK_SOURCE

from .prefect_config import CACHE_TTL, NETWORK_RETRIES  # importing prefect_config sets PREFECT_RESULTS_LOCAL_STORAGE_PATH

# NOTE: do NOT set result_storage here — an unsaved LocalFileSystem block raises
# TypeError at decorator time in Prefect 3.x. Persistence location comes from the
# PREFECT_RESULTS_LOCAL_STORAGE_PATH env var (set in prefect_config on import).
#
# cache_policy is INPUTS + TASK_SOURCE (NOT bare INPUTS): with persist_result=True,
# INPUTS keys the cache on input VALUES only, so the three tasks that all take the
# same sole `COUNTIES` arg (fetch_tracts/fetch_acs/fetch_demographics) would collide
# on ONE key and poison each other's shared persisted result. Adding TASK_SOURCE
# differentiates the keys by each task's source body. This is Prefect's DEFAULT
# minus RUN_ID, so it stays task-distinct while preserving cross-run 7-day resume
# (DEFAULT's RUN_ID component would key each run separately and kill resume).
_CACHE = {
    "cache_policy": INPUTS + TASK_SOURCE,
    "cache_expiration": CACHE_TTL,
    "persist_result": True,
}


# --- Cacheable network tasks (hashable inputs) ---
@task(name="fetch_cbsa_boundary", **NETWORK_RETRIES, **_CACHE)
def fetch_cbsa_boundary_task(cbsa_code: str):
    return get_cbsa_polygon(cbsa_code)


@task(name="fetch_state_zctas", **NETWORK_RETRIES, **_CACHE)
def fetch_state_zctas_task(zip_prefixes):
    return get_state_zctas(zip_prefixes)


@task(name="fetch_tracts", **NETWORK_RETRIES, **_CACHE)
def fetch_tracts_task(counties):
    return get_tracts_for_counties(counties)


@task(name="fetch_acs", **NETWORK_RETRIES, **_CACHE)
def fetch_acs_task(counties):
    frames = [fetch_acs_for_county(s, c) for s, c in counties]
    return compute_acs_features(pd.concat(frames, ignore_index=True))


@task(name="fetch_demographics", **NETWORK_RETRIES, **_CACHE)
def fetch_demographics_task(counties):
    frames = [fetch_demographics_for_county(s, c) for s, c in counties]
    return compute_demographic_percentages(pd.concat(frames, ignore_index=True))


@task(name="fetch_zori", **NETWORK_RETRIES, **_CACHE)
def fetch_zori_task(url: str):
    return fetch_zori_latest(url)


# --- Retry-only network task (GeoDataFrame input; OSM caches internally) ---
@task(name="transit_density", **NETWORK_RETRIES)
def transit_density_task(zctas_for_transit, utm_zone: int):
    return zcta_transit_density(
        zctas_for_transit, transit_filter="", fallback_filter="", utm_zone=utm_zone
    )


# --- Plain CPU tasks ---
@task(name="filter_zctas")
def filter_zctas_task(zctas_all, cbsa_boundary, utm_zone: int):
    return filter_zctas_in_cbsa(zctas_all, cbsa_boundary, utm_zone=utm_zone)


@task(name="map_tracts_to_zctas")
def map_tracts_task(tracts, zctas_in_metro, utm_zone: int):
    return tract_to_zcta_centroid_map(tracts, zctas_in_metro, utm_zone=utm_zone)


# Configure logger for this module
logger = logging.getLogger(__name__)


@flow(name="build-metro", log_prints=True)
def build_metro_flow(metro_key: str = "phoenix") -> str:
    """Execute the full data pipeline to build ZCTA-level housing dataset.

    This function orchestrates a multi-step ETL pipeline that:
    1. Fetches CBSA (metro area) boundary for spatial filtering
    2. Retrieves ZCTA (ZIP code) and census tract geometries
    3. Fetches ACS demographic/commute data at tract level
    4. Maps tracts to ZCTAs via centroid-based spatial join
    5. Aggregates tract data to ZCTA level
    6. Fetches Zillow rent index (ZORI) by ZIP code
    7. Computes OpenStreetMap transit stop density by ZCTA
    8. Merges all data sources into final dataset

    Parameters
    ----------
    metro_key : str
        Key into METRO_CONFIGS (e.g., 'phoenix', 'dallas', 'atlanta').
        Defaults to 'phoenix'.

    Returns
    -------
    str
        Path to the output CSV file.

    Raises
    ------
    requests.HTTPError
        If any API request fails.
    KeyError
        If metro_key is not found in METRO_CONFIGS.
    ValueError
        If no ZCTAs or tracts are found for the metro area.
    """
    _t0 = datetime.now(timezone.utc)
    metro_config = METRO_CONFIGS[metro_key]
    CBSA_CODE = metro_config["cbsa_code"]
    COUNTIES = metro_config["counties"]
    METRO_NAME = metro_config["name"]
    UTM_ZONE = metro_config["utm_zone"]
    ZIP_PREFIXES = metro_config["zip_prefixes"]
    FINAL_ZCTA_OUT = DATA_FINAL / f"final_zcta_dataset_{metro_key}.csv"
    
    logger.info("=" * 60)
    logger.info(f"Building dataset for: {METRO_NAME}")
    logger.info("=" * 60)
    
    # Step 1: Fetch CBSA (metro area) boundary polygon for spatial filtering
    logger.info("STEP 1: Fetching CBSA boundary...")
    cbsa_boundary = fetch_cbsa_boundary_task(CBSA_CODE)
    logger.info(f"Fetched CBSA boundary for: {METRO_NAME}")

    # Step 2: Fetch ZCTA and tract geometries for the region
    logger.info("STEP 2: Loading ZCTA and tract geometries...")
    zctas_all = fetch_state_zctas_task(ZIP_PREFIXES)
    logger.info(f"Fetching census tracts for {len(COUNTIES)} counties across {len(set(s for s, _ in COUNTIES))} state(s)...")
    tracts_all = fetch_tracts_task(COUNTIES)
    logger.info(f"Fetched {len(zctas_all)} ZCTAs and {len(tracts_all)} tracts")

    # Filter ZCTAs to only those within the CBSA (centroid-based)
    zctas_in_metro = filter_zctas_task(zctas_all, cbsa_boundary, UTM_ZONE)
    tracts_in_counties = tracts_all

    # Step 3: Fetch ACS commute data for each county (grouped by state)
    logger.info("STEP 3: Fetching ACS commute data...")
    logger.info(f"Fetching ACS commute data for {len(COUNTIES)} counties...")
    acs_features = fetch_acs_task(COUNTIES)
    logger.info(f"Processed ACS commute data for {len(acs_features)} tracts")
    
    # Step 3b: Fetch ACS demographic data (race, ethnicity, income) for each county
    logger.info("STEP 3b: Fetching ACS demographic data...")
    logger.info(f"Fetching demographic data for {len(COUNTIES)} counties...")
    demo_with_pct = fetch_demographics_task(COUNTIES)
    logger.info(f"Processed demographic data for {len(demo_with_pct)} tracts")

    # Step 4: Map census tracts to ZCTAs using centroid-based spatial join
    # Centroid method assigns each tract to the ZCTA containing its geographic center,
    # avoiding many-to-many relationships that occur with boundary overlaps
    logger.info("STEP 4: Mapping tracts to ZCTAs...")
    logger.info(f"Mapping {len(tracts_in_counties)} tracts to {len(zctas_in_metro)} ZCTAs...")
    tract_to_zcta_map = map_tracts_task(tracts_in_counties, zctas_in_metro, UTM_ZONE)

    if logger.isEnabledFor(logging.DEBUG):
        debug_path = PROJECT_ROOT / "data" / "test" / "debug_tract_to_zcta_map.csv"
        tract_to_zcta_map.to_csv(debug_path, index=False)
        logger.debug("Wrote debug tract-to-ZCTA map to %s", debug_path)

    # Join ACS commute features with tract-to-ZCTA mapping
    acs_with_zcta = acs_features.merge(tract_to_zcta_map, on="GEOID", how="inner")
    
    # Aggregate commute tract-level data to ZCTA level using appropriate statistics
    zcta_aggregated = acs_with_zcta.groupby("ZCTA5CE", as_index=False).agg({
        "rent_to_income": "mean",  # Average rent burden across tracts
        "commute_min_proxy": "mean",  # Average estimated commute time (minutes)
        "ttw_total": "sum",  # Total workers (summed across tracts)
        # Commute time distribution (percentage in each bin)
        "pct_commute_lt10": "mean",  # Average % with commute < 10 min
        "pct_commute_10_19": "mean",  # Average % with commute 10-19 min
        "pct_commute_20_29": "mean",  # Average % with commute 20-29 min
        "pct_commute_30_44": "mean",  # Average % with commute 30-44 min
        "pct_commute_45_59": "mean",  # Average % with commute 45-59 min
        "pct_commute_60_plus": "mean",  # Average % with commute 60+ min
        # Transportation mode share
        "pct_drive_alone": "mean",  # Average % driving alone
        "pct_carpool": "mean",  # Average % carpooling
        "pct_transit": "mean",  # Average % using transit
        "pct_walk": "mean",  # Average % walking
        "pct_wfh": "mean",  # Average % working from home
        "pct_car": "mean",  # Average % using car (alone + carpool)
        # Rent burden
        "pct_rent_burden_30": "mean",  # Average % rent burdened (30%+)
        "pct_rent_burden_50": "mean",  # Average % severely rent burdened (50%+)
        # Tenure and vehicle access (for RQ1 controls)
        "renter_share": "mean",  # Average % of units that are renter-occupied
        "vehicle_access": "mean",  # Average % of households with 1+ vehicles
    })
    logger.info(f"Aggregated commute data to {len(zcta_aggregated)} ZCTAs")
    
    # Aggregate demographic data to ZCTA level (population-weighted)
    zcta_demographics = aggregate_demographics_to_zcta(demo_with_pct, tract_to_zcta_map)
    logger.info(f"Aggregated demographic data to {len(zcta_demographics)} ZCTAs")

    # Step 5: Fetch Zillow Observed Rent Index (ZORI) for rental prices
    logger.info("STEP 5: Fetching Zillow rent data...")
    zori_data = fetch_zori_task(ZORI_ZIP_CSV_URL)
    zori_data = zori_data.rename(columns={"zip": "ZCTA5CE"})
    zori_data["ZCTA5CE"] = zori_data["ZCTA5CE"].astype(str).str.zfill(5)
    logger.info(f"Fetched ZORI data for {len(zori_data)} ZIP codes")

    # Step 6: Compute transit stop density from OpenStreetMap for each ZCTA
    # Empty filter strings use default OSM transit tags defined in config.py
    # (transit_filter and fallback_filter allow custom filtering if needed in future)
    logger.info("STEP 6: Computing transit density...")
    logger.info(f"Computing transit density for {len(zctas_in_metro)} ZCTAs (may take several minutes)...")
    # Create clean GeoDataFrame with only ZCTA ID and geometry to reduce memory footprint
    zctas_for_transit = gpd.GeoDataFrame(
        zctas_in_metro[["ZCTA5CE"]],
        geometry=zctas_in_metro.geometry,
        crs=zctas_in_metro.crs
    )
    transit_density = transit_density_task(zctas_for_transit, UTM_ZONE)
    logger.info(f"Computed transit density for {len(transit_density)} ZCTAs")

    # Step 6b: Calculate population density (people per square km)
    logger.info("Computing population density for ZCTAs...")
    zctas_area = zctas_in_metro.to_crs(UTM_ZONE).copy()
    zctas_area["area_km2"] = zctas_area.geometry.area / 1_000_000  # Convert m² to km²
    zcta_area_df = zctas_area[["ZCTA5CE", "area_km2"]].copy()
    
    # Step 7: Merge all data sources into final dataset
    final_dataset = (
        zcta_aggregated
        .merge(
            zcta_demographics,
            on="ZCTA5CE",
            how="left"  # Left join to keep all ZCTAs
        )
        .merge(
            zori_data[["ZCTA5CE", "period", "zori"]],
            on="ZCTA5CE",
            how="left"  # Left join to keep all ZCTAs even without ZORI data
        )
        .merge(
            transit_density,
            on="ZCTA5CE",
            how="left"  # Left join to keep all ZCTAs even without transit data
        )
        .merge(
            zcta_area_df,
            on="ZCTA5CE",
            how="left"  # Left join to add area for density calculation
        )
    )
    
    # Calculate population density (people per km²)
    final_dataset["pop_density"] = final_dataset["total_pop"] / final_dataset["area_km2"]
    final_dataset = final_dataset.drop(columns=["area_km2"])  # Remove intermediate column
    
    # Step 8: Create income segments based on median income quartiles
    final_dataset = create_income_segments(final_dataset)
    logger.info("Created income segments (Low/Medium/High) based on terciles")

    # Step 9: Reorder columns for consistent output
    column_order = [
        'ZCTA5CE',
        'rent_to_income',
        'pct_rent_burden_30',
        'pct_rent_burden_50',
        'zori',
        'commute_min_proxy',
        'pct_commute_lt10',
        'pct_commute_10_19',
        'pct_commute_20_29',
        'pct_commute_30_44',
        'pct_commute_45_59',
        'pct_commute_60_plus',
        'ttw_total',
        'pct_drive_alone',
        'pct_carpool',
        'pct_car',
        'pct_transit',
        'pct_walk',
        'pct_wfh',
        'renter_share',
        'vehicle_access',
        'total_pop',
        'pop_density',
        'pct_white',
        'pct_black',
        'pct_asian',
        'pct_hispanic',
        'pct_other',
        'median_income',
        'income_segment',
        'stops_per_km2',
        'period'
    ]
    final_dataset = final_dataset[column_order]
    
    # Validate the final dataset against the shared schema contract before writing
    from .schema import validate_final_dataset
    validate_final_dataset(pl.from_pandas(final_dataset))

    # Write output CSV file
    FINAL_ZCTA_OUT.parent.mkdir(parents=True, exist_ok=True)
    final_dataset.to_csv(FINAL_ZCTA_OUT, index=False)

    # Emit provenance manifest (sha256 + schema + source vintages) for this run
    from .manifest import build_manifest, get_git_commit, write_manifest
    zori_period = None
    if "period" in final_dataset.columns and final_dataset["period"].notna().any():
        zori_period = str(final_dataset["period"].dropna().max())
    manifest = build_manifest(
        metro_key,
        FINAL_ZCTA_OUT,
        git_commit=get_git_commit(),
        timestamp_utc=_t0.isoformat(),
        zori_period=zori_period,
        steps=[],  # per-step timing can be threaded later; empty list is valid
    )
    write_manifest(manifest, DATA_FINAL / f"{metro_key}.manifest.json")

    logger.info("=" * 60)
    logger.info(f"SUCCESS: Wrote {len(final_dataset)} ZCTAs to {FINAL_ZCTA_OUT.name}")
    logger.info(f"Output: {FINAL_ZCTA_OUT}")
    logger.info("=" * 60)

    return str(FINAL_ZCTA_OUT)


def build_final_dataset(metro_key: str = "phoenix") -> str:
    """Public entry point — delegates to the Prefect flow. Signature preserved."""
    return build_metro_flow(metro_key)