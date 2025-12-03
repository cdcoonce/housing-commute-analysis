"""Census TIGER/Line geographic boundary fetching via REST APIs.

This module retrieves geographic boundaries (polygons) for Census geographies
including CBSAs (metro areas), ZCTAs (ZIP codes), and census tracts from the
Census Bureau's TIGER/Line web services.
"""
from __future__ import annotations

import geopandas as gpd
import pandas as pd

from .config import ZIP_PREFIXES
from .utils import esri_geojson_to_gdf

# Census TIGER/Line REST API endpoints
TIGER_CBSA_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
    "TIGERweb/CBSA/MapServer/15/query"
)
TIGER_ZCTA_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
    "TIGERweb/tigerWMS_ACS2024/MapServer/2/query"
)
# Layer 7 is Census Tracts (ACS 2024), Layer 8 is Block Groups
TIGER_TRACTS_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
    "TIGERweb/Tracts_Blocks/MapServer/7/query"
)


def get_cbsa_polygon(cbsa_code: str) -> gpd.GeoDataFrame:
    """Fetch the boundary polygon for a Core-Based Statistical Area (CBSA).
    
    CBSAs are metro/micropolitan areas defined by the Office of Management and
    Budget. This function retrieves the boundary polygon for spatial filtering.
    
    Args:
        cbsa_code: 5-digit CBSA code (e.g., '38060' for Phoenix metro)
        
    Returns:
        GeoDataFrame with one row containing CBSA, NAME, and geometry columns
        
    Raises:
        requests.HTTPError: If the TIGER API request fails
        
    Example:
        >>> phoenix = get_cbsa_polygon('38060')
        >>> print(phoenix['NAME'].iloc[0])
        Phoenix-Mesa-Chandler, AZ Metro Area
    """
    params = {
        "where": f"CBSA='{cbsa_code}'",
        "outFields": "CBSA,NAME",
        "returnGeometry": "true",
        "f": "geojson"
    }
    return esri_geojson_to_gdf(TIGER_CBSA_URL, params)

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
        Empty GeoDataFrame if no ZCTAs found.
        
    Raises:
        requests.HTTPError: If the TIGER API request fails
        
    Note:
        - Uses pagination (100 records per batch) to avoid API timeouts
        - ZCTAs are approximations and don't perfectly match USPS ZIP codes
        - Some ZIP codes have no ZCTA (e.g., PO boxes, single buildings)
        - Progress messages are printed for each batch fetched
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
        for prefix in prefixes:
            offset = 0
            max_records = 100  # Batch size to balance speed and API stability
            
            while True:
                params = {
                    "where": f"ZCTA5 LIKE '{prefix}%'",
                    "outFields": "ZCTA5,GEOID,NAME",
                    "returnGeometry": "true",
                    "f": "geojson",
                    "resultOffset": offset,
                    "resultRecordCount": max_records
                }
                
                try:
                    chunk = esri_geojson_to_gdf(TIGER_ZCTA_URL, params)
                    if chunk.empty:
                        break
                    
                    zcta_chunks.append(chunk)
                    print(f"Fetched {len(chunk)} ZCTAs for prefix '{prefix}' "
                          f"(offset {offset})")
                    
                    # Stop if we got fewer records than requested (last page)
                    if len(chunk) < max_records:
                        break
                    
                    offset += max_records
                    
                except ConnectionError as e:
                    print(f"Network error fetching ZCTAs for prefix '{prefix}' "
                          f"at offset {offset}: {e}")
                    break
                except TimeoutError:
                    print(f"Timeout fetching ZCTAs for prefix '{prefix}' "
                          f"at offset {offset}. Try reducing max_records or checking network.")
                    break
                except ValueError as e:
                    print(f"Invalid response data for prefix '{prefix}' "
                          f"at offset {offset}: {e}")
                    break
                except Exception as e:
                    print(f"Unexpected error fetching ZCTAs for prefix '{prefix}' "
                          f"at offset {offset}: {type(e).__name__}: {e}")
                    break
        
        # Combine all fetched chunks
        if zcta_chunks:
            combined = pd.concat(zcta_chunks, ignore_index=True)
            zcta_data = gpd.GeoDataFrame(combined, crs="EPSG:4326")
        else:
            zcta_data = gpd.GeoDataFrame(
                columns=["ZCTA5", "GEOID", "NAME", "geometry"],
                geometry="geometry",
                crs="EPSG:4326"
            )
    
    # Standardize column name to ZCTA5CE for consistency across modules
    if "ZCTA5" in zcta_data.columns:
        zcta_data = zcta_data.rename(columns={"ZCTA5": "ZCTA5CE"})
    
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
            print(f"  Fetched {len(gdf)} tracts for state {state_fips}, county {county_fips}")
    
    if tract_gdfs:
        return pd.concat(tract_gdfs, ignore_index=True)
    else:
        return gpd.GeoDataFrame(
            columns=["GEOID", "STATE", "COUNTY", "NAME", "geometry"],
            geometry="geometry",
            crs="EPSG:4326"
        )
