"""Unit tests for src/pipelines/osm.py (all offline).

zcta_transit_density's fallback bus-stop query (issue #22) must log a warning
when it hits an exception type that is neither an "empty Overpass response"
(expected, no data) nor a ConnectionError/TimeoutError (already logged) --
unexpected errors must not be swallowed silently.
"""
from __future__ import annotations

import logging

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

import src.pipelines.osm as osm


def _zcta_gdf() -> gpd.GeoDataFrame:
    """Single-ZCTA GeoDataFrame with a small square polygon."""
    square = Polygon([(-90.01, 35.0), (-90.0, 35.0), (-90.0, 35.01), (-90.01, 35.01)])
    return gpd.GeoDataFrame(
        {"ZCTA5CE": ["38103"]},
        geometry=[square],
        crs="EPSG:4326",
    )


def _empty_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")


def test_fallback_query_logs_unexpected_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An unexpected exception from the fallback bus-stop query is logged."""
    calls = {"n": 0}

    def fake_features_from_polygon(polygon, tags):
        calls["n"] += 1
        if calls["n"] == 1:
            # Primary public_transport query: no data found (expected, silent).
            return _empty_gdf()
        # Fallback bus_stop query: an unexpected, non-network error.
        raise ValueError("malformed query")

    monkeypatch.setattr(osm.ox, "features_from_polygon", fake_features_from_polygon, raising=False)
    monkeypatch.setattr(osm.ox, "geometries_from_polygon", None, raising=False)

    with caplog.at_level(logging.WARNING, logger=osm.logger.name):
        result = osm.zcta_transit_density(_zcta_gdf(), "transit_tags", "fallback_tags")

    assert any(
        "38103" in record.message and "ValueError" in record.message
        for record in caplog.records
    ), caplog.records

    assert result.loc[0, "stops_per_km2"] == 0.0
