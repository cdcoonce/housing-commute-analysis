"""Spatial operations for filtering and mapping census geographies.

This module handles geographic filtering and centroid-based spatial joins
between different census geographies (ZCTAs, tracts, CBSAs) with proper
coordinate system transformations for accurate calculations.
"""
from __future__ import annotations

import geopandas as gpd
import pandas as pd

from .config import UTM_ZONE


def filter_zctas_in_cbsa(
    zcta_gdf: gpd.GeoDataFrame, 
    cbsa_gdf: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Filter ZCTAs to only those whose centroids fall within a CBSA boundary.
    
    Uses centroid-based filtering rather than intersection to avoid edge cases
    where a ZCTA partially overlaps the boundary. Projects to appropriate UTM
    zone for accurate centroid calculation before testing containment.
    
    Args:
        zcta_gdf: GeoDataFrame of ZIP Code Tabulation Areas
        cbsa_gdf: GeoDataFrame containing one CBSA (Core-Based Statistical Area) polygon
        
    Returns:
        Subset of zcta_gdf where ZCTA centroids are within the CBSA boundary
    """
    # Project to UTM for accurate centroid calculation (meters, not degrees)
    zcta_projected = zcta_gdf.to_crs(UTM_ZONE)
    zcta_with_centroids = zcta_projected.copy()
    zcta_with_centroids["centroid"] = zcta_with_centroids.geometry.centroid
    
    # Project centroids back to WGS84 for comparison with CBSA boundary
    zcta_with_centroids = zcta_with_centroids.set_geometry("centroid").to_crs(4326)
    
    # Test which centroids are within the CBSA polygon
    cbsa_boundary = cbsa_gdf.iloc[0].geometry
    is_within_cbsa = zcta_with_centroids["centroid"].within(cbsa_boundary)
    
    # Return original ZCTA geometries (not centroids) for those within CBSA
    return zcta_gdf.loc[is_within_cbsa].copy()


def tract_to_zcta_centroid_map(
    tracts_gdf: gpd.GeoDataFrame, 
    zctas_gdf: gpd.GeoDataFrame
) -> pd.DataFrame:
    """Map census tracts to ZCTAs using centroid-based spatial join.
    
    Assigns each census tract to a ZCTA by testing which ZCTA polygon contains
    the tract's centroid. This provides a deterministic one-to-one mapping.
    
    Args:
        tracts_gdf: GeoDataFrame of census tracts with GEOID column
        zctas_gdf: GeoDataFrame of ZCTAs with ZCTA5CE column
        
    Returns:
        DataFrame with columns [GEOID, ZCTA5CE] mapping tract IDs to ZIP codes.
        Duplicates are removed (should not occur with proper tract data).
        
    Note:
        Uses UTM projection for accurate centroid calculation. Some tracts may
        not be assigned if their centroids fall outside all ZCTA polygons.
    """
    # Project to UTM for accurate centroid calculation
    tracts_projected = tracts_gdf.to_crs(UTM_ZONE).copy()
    tracts_projected["centroid"] = tracts_projected.geometry.centroid
    tracts_projected = tracts_projected.set_geometry("centroid", crs=UTM_ZONE)
    
    # Project back to WGS84 for spatial join with ZCTAs
    tracts_with_centroids = tracts_projected.to_crs(4326)
    zctas_for_join = zctas_gdf.to_crs(4326)
    
    # Spatial join: find which ZCTA polygon contains each tract centroid
    joined = gpd.sjoin(
        tracts_with_centroids,
        zctas_for_join[["ZCTA5CE", "geometry"]],
        how="inner",
        predicate="within"
    )
    
    # Extract mapping and ensure 5-digit ZIP code format
    tract_zcta_mapping = joined[["GEOID", "ZCTA5CE"]].drop_duplicates().copy()
    tract_zcta_mapping["ZCTA5CE"] = (
        tract_zcta_mapping["ZCTA5CE"].astype(str).str.zfill(5)
    )
    
    return pd.DataFrame(tract_zcta_mapping)