"""Census TIGER/Line geographic boundary fetching via REST APIs.

This module retrieves geographic boundaries (polygons) for Census geographies
including CBSAs (metro areas), ZCTAs (ZIP codes), and census tracts from the
Census Bureau's TIGER/Line web services.
"""
from __future__ import annotations

import logging

import geopandas as gpd
import pandas as pd
import requests

from .config import ZIP_PREFIXES
from .utils import esri_geojson_to_gdf, http_json_to_dict

# Configure logger for this module
logger = logging.getLogger(__name__)

# Census TIGER/Line REST API endpoints
TIGER_CBSA_BASE_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
    "TIGERweb/CBSA/MapServer"
)
# Pinned CBSA delineation vintage (issue #2). TIGERweb inserts new vintage
# groups into this MapServer and reshuffles layer ids (an "ACS 2025" group
# shifted the Census-2020 layers from 15-16 to 26-27), so the layer is
# resolved from the service's layer listing by vintage-group name instead of
# a hardcoded index. "ACS 2024" carries the 2023 OMB delineations — the
# vintage the committed 9-metro datasets were built against. Changing this
# constant is a deliberate delineation change and requires a full rebuild
# through scripts/rebuild_gate.py.
CBSA_VINTAGE = "ACS 2024"
CBSA_LAYER_NAME = "Metropolitan Statistical Areas"

# Per-process cache of resolved layer ids, keyed by (base_url, vintage):
# one layer-listing fetch serves every metro in a run. Deliberately module-
# level (not Prefect-cached) so a fresh process always re-resolves.
_cbsa_layer_cache: dict[tuple[str, str], int] = {}
TIGER_ZCTA_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
    "TIGERweb/tigerWMS_ACS2024/MapServer/2/query"
)
# Layer 7 is Census Tracts (ACS 2024), Layer 8 is Block Groups
TIGER_TRACTS_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
    "TIGERweb/Tracts_Blocks/MapServer/7/query"
)


def resolve_cbsa_layer_id(
    base_url: str = TIGER_CBSA_BASE_URL,
    vintage: str = CBSA_VINTAGE,
) -> int:
    """Resolve the CBSA MapServer layer id for the pinned delineation vintage.

    Queries the MapServer's layer listing (``{base_url}?f=json``) and selects
    the ``CBSA_LAYER_NAME`` feature layer nested under the top-level vintage
    group named ``vintage``. Never falls back to a hardcoded index: if the
    vintage group is missing or the match is not unique, the service has been
    reorganized under us and the build must stop rather than silently switch
    delineation vintages.

    Args:
        base_url: MapServer root URL (no trailing slash, no layer id)
        vintage: Top-level vintage group name (e.g. 'ACS 2024', 'Census 2020')

    Returns:
        The layer id to query, cached per process per (base_url, vintage).

    Raises:
        requests.RequestException: If the layer-listing request fails
        ValueError: If the listing has no layers, the vintage group is absent,
            or the layer match is missing/ambiguous
    """
    cache_key = (base_url, vintage)
    if cache_key in _cbsa_layer_cache:
        return _cbsa_layer_cache[cache_key]

    listing = http_json_to_dict(base_url, params={"f": "json"})
    layers = listing.get("layers") if isinstance(listing, dict) else None
    if not layers:
        raise ValueError(
            f"no layers in MapServer listing from {base_url}; cannot resolve "
            f"CBSA vintage {vintage!r}"
        )

    layers_by_id = {layer["id"]: layer for layer in layers}
    vintage_group_ids = {
        layer["id"]
        for layer in layers
        if layer.get("name") == vintage and layer.get("type") == "Group Layer"
    }
    if not vintage_group_ids:
        raise ValueError(
            f"CBSA vintage group {vintage!r} not found in TIGERweb layer "
            f"listing at {base_url}; refusing to fall back to a layer index"
        )

    def _under_vintage(layer: dict) -> bool:
        parent_id = layer.get("parentLayerId", -1)
        while parent_id is not None and parent_id != -1:
            if parent_id in vintage_group_ids:
                return True
            parent = layers_by_id.get(parent_id)
            if parent is None:
                return False
            parent_id = parent.get("parentLayerId", -1)
        return False

    matches = [
        layer
        for layer in layers
        if layer.get("name") == CBSA_LAYER_NAME
        and layer.get("type") == "Feature Layer"
        and _under_vintage(layer)
    ]
    if len(matches) != 1:
        detail = (
            f"ids {sorted(layer['id'] for layer in matches)}" if matches else "none"
        )
        raise ValueError(
            f"{'ambiguous' if matches else 'no'} {CBSA_LAYER_NAME!r} match "
            f"under CBSA vintage {vintage!r} at {base_url} ({detail}); "
            "refusing to guess a layer"
        )

    layer_id = matches[0]["id"]
    logger.info(f"Resolved CBSA layer for vintage {vintage!r}: id {layer_id}")
    _cbsa_layer_cache[cache_key] = layer_id
    return layer_id


def get_cbsa_polygon(cbsa_code: str) -> gpd.GeoDataFrame:
    """Fetch the boundary polygon for a Core-Based Statistical Area (CBSA).

    CBSAs are metro/micropolitan areas defined by the Office of Management and
    Budget. This function retrieves the boundary polygon for spatial filtering,
    from the layer serving the pinned ``CBSA_VINTAGE`` delineations (resolved
    by name at fetch time — TIGERweb reorders layer ids between vintages).

    Args:
        cbsa_code: 5-digit CBSA code (e.g., '38060' for Phoenix metro)

    Returns:
        GeoDataFrame with one row containing CBSA, NAME, and geometry columns

    Raises:
        requests.HTTPError: If the TIGER API request fails
        ValueError: If the pinned vintage cannot be resolved to exactly one layer

    Example:
        >>> phoenix = get_cbsa_polygon('38060')
        >>> print(phoenix['NAME'].iloc[0])
        Phoenix-Mesa-Chandler, AZ Metro Area
    """
    layer_id = resolve_cbsa_layer_id()
    params = {
        "where": f"CBSA='{cbsa_code}'",
        "outFields": "CBSA,NAME",
        "returnGeometry": "true",
        "f": "geojson"
    }
    return esri_geojson_to_gdf(f"{TIGER_CBSA_BASE_URL}/{layer_id}/query", params)

def get_state_zctas(
    zip_prefixes: list[str] | None = None
) -> gpd.GeoDataFrame:
    """Fetch ZIP Code Tabulation Area (ZCTA) boundaries by ZIP prefix.
    
    ZCTAs are generalized areal representations of USPS ZIP codes. This function
    fetches ZCTA polygons by querying for specific ZIP prefixes (e.g., '85' for
    Phoenix area) to limit the result set and avoid API timeouts.
    
    Args:
        zip_prefixes: List of 2-digit ZIP prefixes (e.g., ['85', '86']). If None,
                     uses ZIP_PREFIXES from config. If empty list, queries all
                     ZCTAs (slow and may timeout).
                     
    Returns:
        GeoDataFrame with columns: ZCTA5CE (5-digit ZIP), GEOID, NAME, geometry.
        Each ZCTA5CE appears exactly once, even when prefixes overlap (e.g.
        '38' and '386' both fetch 386xx ZCTAs).

    Raises:
        requests.RequestException: If any TIGER API request fails during any
            prefix's pagination. Failures propagate so a wrapping retry layer
            (e.g. a Prefect task) sees them — a swallowed failure here would
            silently drop every ZCTA for that prefix and cache the truncated
            result as a success.
        ValueError: If any configured prefix contributes zero ZCTAs (guards
            against any silent-truncation path).

    Note:
        - Uses pagination (100 records per batch) to avoid API timeouts
        - ZCTAs are approximations and don't perfectly match USPS ZIP codes
        - Some ZIP codes have no ZCTA (e.g., PO boxes, single buildings)
        - Progress messages are logged for each batch fetched
    """
    prefixes = zip_prefixes or ZIP_PREFIXES
    
    if not prefixes:
        # Fallback: query all ZCTAs (not recommended, very slow)
        params = {
            "where": "1=1",
            "outFields": "ZCTA5,GEOID,NAME",
            "returnGeometry": "true",
            "f": "geojson",
            "resultRecordCount": 100
        }
        zcta_data = esri_geojson_to_gdf(TIGER_ZCTA_URL, params)
    else:
        # Query by ZIP prefix with pagination to avoid timeouts
        zcta_chunks = []
        empty_prefixes = []
        for prefix in prefixes:
            offset = 0
            max_records = 100  # Batch size to balance speed and API stability
            prefix_count = 0

            while True:
                params = {
                    "where": f"ZCTA5 LIKE '{prefix}%'",
                    "outFields": "ZCTA5,GEOID,NAME",
                    "returnGeometry": "true",
                    "f": "geojson",
                    "resultOffset": offset,
                    "resultRecordCount": max_records
                }

                # Fetch failures must propagate: swallowing one here would
                # silently drop the rest of this prefix while the function
                # "succeeds", defeating task-level retries and poisoning any
                # downstream cache with a truncated result.
                try:
                    chunk = esri_geojson_to_gdf(TIGER_ZCTA_URL, params)
                except requests.RequestException:
                    logger.error(
                        f"Request failed fetching ZCTAs for prefix '{prefix}' "
                        f"at offset {offset}; propagating for retry"
                    )
                    raise

                if chunk.empty:
                    break

                zcta_chunks.append(chunk)
                prefix_count += len(chunk)
                logger.info(
                    f"Fetched {len(chunk)} ZCTAs for prefix '{prefix}' (offset {offset})"
                )

                # Stop if we got fewer records than requested (last page)
                if len(chunk) < max_records:
                    break

                offset += max_records

            if prefix_count == 0:
                empty_prefixes.append(prefix)

        # Coverage guard: every configured prefix must contribute ZCTAs.
        if empty_prefixes:
            raise ValueError(
                f"No ZCTAs returned for zip prefix(es) {empty_prefixes}; "
                "refusing to return a truncated result"
            )

        combined = pd.concat(zcta_chunks, ignore_index=True)
        zcta_data = gpd.GeoDataFrame(combined, crs="EPSG:4326")

    # Standardize column name to ZCTA5CE for consistency across modules
    if "ZCTA5" in zcta_data.columns:
        zcta_data = zcta_data.rename(columns={"ZCTA5": "ZCTA5CE"})

    # Overlapping prefixes (e.g. '38' and '386') refetch the same national-layer
    # ZCTAs; duplicates are exact refetches, so keep the first of each.
    if "ZCTA5CE" in zcta_data.columns:
        zcta_data = zcta_data.drop_duplicates(subset="ZCTA5CE", ignore_index=True)

    return zcta_data

def get_state_tracts(
    state_fips: str, 
    county_list: list[str] | None = None
) -> gpd.GeoDataFrame:
    """Fetch census tract boundaries for a state or specific counties.
    
    Census tracts are small statistical subdivisions of a county, typically
    containing 1,200-8,000 people. When county_list is provided, fetches tracts
    county-by-county to avoid API response size limits for large states.
    
    Args:
        state_fips: Two-digit state FIPS code (e.g., '04' for Arizona)
        county_list: Optional list of 3-digit county FIPS codes. If provided,
                    only tracts within these counties are returned. Recommended
                    for large states to avoid API timeouts.
                    
    Returns:
        GeoDataFrame with columns: GEOID (11-digit tract ID), STATE, COUNTY,
        NAME, geometry. Empty GeoDataFrame if no tracts found.
        
    Raises:
        requests.HTTPError: If the TIGER API request fails
        
    Note:
        Querying entire state without county_list may fail for populous states
        (e.g., California, Texas) due to API response size limits.
    """
    if county_list:
        # Fetch tracts county-by-county to stay within API limits
        tract_gdfs = []
        for county_fips in county_list:
            params = {
                "where": f"STATE='{state_fips}' AND COUNTY='{county_fips}'",
                "outFields": "GEOID,STATE,COUNTY,NAME",
                "returnGeometry": "true",
                "f": "geojson"
            }
            county_tracts = esri_geojson_to_gdf(TIGER_TRACTS_URL, params)
            if not county_tracts.empty:
                tract_gdfs.append(county_tracts)
        
        # Combine all counties or return empty GeoDataFrame
        if tract_gdfs:
            combined = pd.concat(tract_gdfs, ignore_index=True)
            return gpd.GeoDataFrame(combined, crs="EPSG:4326")
        return gpd.GeoDataFrame(
            columns=["GEOID", "STATE", "COUNTY", "NAME", "geometry"],
            geometry="geometry",
            crs="EPSG:4326"
        )
    else:
        # Fetch entire state at once (may fail for large states)
        params = {
            "where": f"STATE='{state_fips}'",
            "outFields": "GEOID,STATE,COUNTY,NAME",
            "returnGeometry": "true",
            "f": "geojson"
        }
        return esri_geojson_to_gdf(TIGER_TRACTS_URL, params)


def get_tracts_for_counties(
    counties: list[tuple[str, str]]
) -> gpd.GeoDataFrame:
    """Fetch census tracts for multiple state-county pairs.
    
    This function supports multi-state metro areas by fetching tracts for
    counties across different states and combining them into a single GeoDataFrame.
    
    Args:
        counties: List of (state_fips, county_fips) tuples
                 e.g., [("47", "157"), ("05", "035"), ("28", "033")]
                 
    Returns:
        GeoDataFrame with all tracts from specified counties, with columns:
        GEOID (11-digit), STATE, COUNTY, NAME, geometry
        
    Raises:
        requests.HTTPError: If any TIGER API request fails
        
    Example:
        >>> memphis_counties = [("47", "157"), ("05", "035"), ("28", "033")]
        >>> tracts = get_tracts_for_counties(memphis_counties)
        >>> print(f"Fetched {len(tracts)} tracts across {len(memphis_counties)} counties")
    """
    tract_gdfs = []
    
    for state_fips, county_fips in counties:
        params = {
            "where": f"STATE='{state_fips}' AND COUNTY='{county_fips}'",
            "outFields": "GEOID,STATE,COUNTY,NAME",
            "returnGeometry": "true",
            "f": "geojson"
        }
        gdf = esri_geojson_to_gdf(TIGER_TRACTS_URL, params)
        if not gdf.empty:
            tract_gdfs.append(gdf)
            logger.info(f"  Fetched {len(gdf)} tracts for state {state_fips}, county {county_fips}")
    
    if tract_gdfs:
        return pd.concat(tract_gdfs, ignore_index=True)
    else:
        return gpd.GeoDataFrame(
            columns=["GEOID", "STATE", "COUNTY", "NAME", "geometry"],
            geometry="geometry",
            crs="EPSG:4326"
        )
