"""OpenStreetMap transit stop density calculation via OSMnx.

This module queries OpenStreetMap data to count public transit stops/stations
within each ZCTA and computes density metrics for transit accessibility analysis.
"""
from __future__ import annotations

import logging

import geopandas as gpd
import osmnx as ox
import pandas as pd

from .config import CACHE_DIR

# Configure logger for this module
logger = logging.getLogger(__name__)

# Configure OSMnx to use our centralized cache directory
ox.settings.cache_folder = str(CACHE_DIR / "osm")
ox.settings.use_cache = True


def zcta_transit_density(
    zcta_gdf: gpd.GeoDataFrame, 
    transit_filter: str, 
    fallback_filter: str
) -> pd.DataFrame:
    """Calculate public transit stop density for each ZCTA using OpenStreetMap.
    
    Queries OSM for transit features (platforms, stops, stations) within each
    ZCTA polygon and computes stops per square kilometer as a transit accessibility
    metric. Falls back to bus_stop query if no public_transport features found.
    
    Args:
        zcta_gdf: GeoDataFrame with ZCTA5CE and geometry columns
        transit_filter: OSM tag filter for transit features (currently unused,
                       hardcoded to {"public_transport": True})
        fallback_filter: Fallback OSM filter (currently unused, hardcoded to
                        {"highway": "bus_stop"})
        
    Returns:
        DataFrame with columns [ZCTA5CE, stops_per_km2]. One row per input ZCTA.
        
    Note:
        - Queries OSM in WGS84 (EPSG:4326) as required by OSMnx
        - Computes area in Web Mercator (EPSG:3857) for consistent km² calculation
        - OSM data completeness varies by region; results may undercount actual stops
        - Compatible with both osmnx < 1.0 (geometries_from_polygon) and 
          osmnx >= 1.0 (features_from_polygon) APIs
        - Silent failures return 0 stops if OSM query fails
    """
    # Ensure data is in WGS84 for OSMnx queries
    zctas_wgs84 = zcta_gdf.to_crs(4326)
    
    transit_densities = []
    
    for _, zcta_row in zctas_wgs84.iterrows():
        polygon = zcta_row.geometry
        
        # Try to fetch public transit features (platforms, stops, stations)
        # Try both API names for compatibility with different OSMnx versions
        try:
            # Try newer API first (osmnx >= 1.0)
            if hasattr(ox, 'features_from_polygon'):
                transit_features = ox.features_from_polygon(
                    polygon, 
                    tags={"public_transport": True}
                )
            else:
                # Fall back to older API (osmnx < 1.0)
                transit_features = ox.geometries_from_polygon(
                    polygon, 
                    tags={"public_transport": True}
                )
        except AttributeError:
            # OSMnx API not found - skip transit data for this ZCTA
            logger.warning(
                f"OSMnx API function not available for ZCTA {zcta_row['ZCTA5CE']}"
            )
            transit_features = gpd.GeoDataFrame(geometry=[], crs=4326)
        except Exception as e:
            # No data or other errors - handle based on exception type
            error_type = type(e).__name__
            if 'InsufficientResponseError' in error_type or 'EmptyOverpassResponse' in error_type:
                # No OSM features match the query in this area (expected)
                transit_features = gpd.GeoDataFrame(geometry=[], crs=4326)
            elif isinstance(e, (ConnectionError, TimeoutError)):
                # Network connectivity issues - log and continue with zero stops
                logger.warning(
                    f"Network error querying OSM for ZCTA {zcta_row['ZCTA5CE']}: {e}"
                )
                transit_features = gpd.GeoDataFrame(geometry=[], crs=4326)
            else:
                # Other unexpected errors - log but continue
                logger.warning(
                    f"Error querying OSM for ZCTA {zcta_row['ZCTA5CE']}: {error_type}: {e}"
                )
                transit_features = gpd.GeoDataFrame(geometry=[], crs=4326)
        
        # Fallback: query for bus stops if no public_transport features found
        if transit_features.empty:
            try:
                # Try both API names for compatibility
                if hasattr(ox, 'features_from_polygon'):
                    transit_features = ox.features_from_polygon(
                        polygon, 
                        tags={"highway": "bus_stop"}
                    )
                else:
                    transit_features = ox.geometries_from_polygon(
                        polygon, 
                        tags={"highway": "bus_stop"}
                    )
            except AttributeError:
                # OSMnx API not found - skip
                transit_features = gpd.GeoDataFrame(geometry=[], crs=4326)
            except Exception as e:
                # Handle errors silently for fallback (expected to often fail)
                error_type = type(e).__name__
                if 'InsufficientResponseError' not in error_type and 'EmptyOverpassResponse' not in error_type:
                    # Only log unexpected errors, not "no data found" errors
                    if not isinstance(e, (ConnectionError, TimeoutError)):
                        pass  # Silent failure for fallback query
                transit_features = gpd.GeoDataFrame(geometry=[], crs=4326)
        
        # Project to Web Mercator for counting (only if features exist)
        if not transit_features.empty:
            transit_features = transit_features.to_crs(3857)
        
        # Calculate ZCTA area in square kilometers using Web Mercator projection
        area_km2 = (
            gpd.GeoSeries(polygon, crs=4326)
            .to_crs(3857)
            .area
            .iloc[0] / 1_000_000  # Convert m² to km²
        )
        
        # Compute transit stop density
        stop_count = len(transit_features)
        density = stop_count / area_km2 if area_km2 > 0 else 0.0
        
        transit_densities.append({
            "ZCTA5CE": str(zcta_row["ZCTA5CE"]).zfill(5),
            "stops_per_km2": density
        })
    
    return pd.DataFrame(transit_densities)