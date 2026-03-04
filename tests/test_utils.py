"""Tests for src.pipelines.utils module."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import geopandas as gpd
from urllib3.util.retry import Retry

from src.pipelines.utils import _get_session, esri_geojson_to_gdf


def test_get_session_has_retry():
    """Session HTTPS adapter must use a Retry with total=3."""
    session = _get_session()
    adapter = session.get_adapter("https://")
    retry: Retry = adapter.max_retries

    assert isinstance(retry, Retry)
    assert retry.total == 3


def test_get_session_mounts_https():
    """Session must have an adapter mounted for the https:// prefix."""
    session = _get_session()
    adapter = session.get_adapter("https://example.com")

    assert adapter is not None


@patch("src.pipelines.utils._get_session")
def test_esri_geojson_to_gdf_valid(mock_get_session: MagicMock):
    """Valid ESRI JSON with features returns a GeoDataFrame with correct rows."""
    esri_response = {
        "features": [
            {
                "attributes": {"NAME": "test"},
                "geometry": {"type": "Point", "coordinates": [-111.9, 33.4]},
            },
            {
                "attributes": {"NAME": "test2"},
                "geometry": {"type": "Point", "coordinates": [-112.0, 33.5]},
            },
        ]
    }

    mock_response = MagicMock()
    mock_response.json.return_value = esri_response
    mock_response.raise_for_status.return_value = None

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response
    mock_get_session.return_value = mock_session

    gdf = esri_geojson_to_gdf("https://example.com/query", params={"where": "1=1"})

    assert isinstance(gdf, gpd.GeoDataFrame)
    assert len(gdf) == 2
    assert list(gdf["NAME"]) == ["test", "test2"]


@patch("src.pipelines.utils._get_session")
def test_esri_geojson_to_gdf_empty_features(mock_get_session: MagicMock):
    """Empty features list returns an empty GeoDataFrame."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"features": []}
    mock_response.raise_for_status.return_value = None

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response
    mock_get_session.return_value = mock_session

    gdf = esri_geojson_to_gdf("https://example.com/query", params={"where": "1=1"})

    assert isinstance(gdf, gpd.GeoDataFrame)
    assert len(gdf) == 0
