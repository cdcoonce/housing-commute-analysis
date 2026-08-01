"""Unit tests for src/pipelines/spatial.py.

filter_zctas_in_cbsa and tract_to_zcta_centroid_map are the CRS-transform +
centroid-containment logic that every metro's build_metro_flow depends on
(build.py's filter_zctas_task and map_tracts_task). All fixtures use
Phoenix-plausible WGS84 (crs=4326) coordinates and the default utm_zone
(32612, UTM Zone 12N).
"""
from __future__ import annotations

import geopandas as gpd
from shapely.geometry import box

import src.pipelines.spatial as spatial


def test_filter_zctas_in_cbsa_keeps_inside_drops_outside() -> None:
    """Only the ZCTA whose centroid falls inside the CBSA polygon survives,
    and the returned frame keeps the original polygon geometry (not the
    centroid used internally to test containment)."""
    cbsa_gdf = gpd.GeoDataFrame(
        {"CBSA": ["38060"]},
        geometry=[box(-112.5, 33.0, -111.5, 34.0)],
        crs=4326,
    )
    zcta_gdf = gpd.GeoDataFrame(
        {"ZCTA5CE": ["85001", "85501"]},
        geometry=[
            box(-112.1, 33.4, -111.9, 33.6),  # centroid (-112.0, 33.5): inside
            box(-110.6, 33.4, -110.4, 33.6),  # centroid (-110.5, 33.5): outside
        ],
        crs=4326,
    )

    result = spatial.filter_zctas_in_cbsa(zcta_gdf, cbsa_gdf)

    assert list(result["ZCTA5CE"]) == ["85001"]
    assert (result.geom_type == "Polygon").all()
    assert result.crs == zcta_gdf.crs
    assert "centroid" not in result.columns


def test_tract_to_zcta_centroid_map_zero_pads_short_zcta() -> None:
    """A ZCTA5CE that's shorter than 5 digits (leading zero dropped upstream)
    must be zero-padded back to a 5-digit ZIP in the output."""
    tracts_gdf = gpd.GeoDataFrame(
        {"GEOID": ["040139501001"]},
        geometry=[box(-112.001, 33.499, -111.999, 33.501)],
        crs=4326,
    )
    zctas_gdf = gpd.GeoDataFrame(
        {"ZCTA5CE": ["851"]},
        geometry=[box(-112.5, 33.0, -111.5, 34.0)],
        crs=4326,
    )

    result = spatial.tract_to_zcta_centroid_map(tracts_gdf, zctas_gdf)

    assert len(result) == 1
    assert result.iloc[0]["GEOID"] == "040139501001"
    assert result.iloc[0]["ZCTA5CE"] == "00851"


def test_tract_to_zcta_centroid_map_drops_duplicate_rows() -> None:
    """Two overlapping ZCTA polygons sharing one ZCTA5CE both contain the
    tract's centroid, so the spatial join yields two matching rows; the
    output must collapse them to exactly one."""
    tracts_gdf = gpd.GeoDataFrame(
        {"GEOID": ["040139501001"]},
        geometry=[box(-112.001, 33.499, -111.999, 33.501)],
        crs=4326,
    )
    zctas_gdf = gpd.GeoDataFrame(
        {"ZCTA5CE": ["86001", "86001"]},
        geometry=[
            box(-112.2, 33.3, -111.8, 33.7),
            box(-112.3, 33.2, -111.7, 33.8),
        ],
        crs=4326,
    )

    result = spatial.tract_to_zcta_centroid_map(tracts_gdf, zctas_gdf)

    assert len(result) == 1
    assert result.iloc[0]["ZCTA5CE"] == "86001"
