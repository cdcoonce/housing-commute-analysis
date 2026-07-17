"""Unit tests for src/pipelines/tiger.py (all offline).

get_state_zctas fetches one paginated TIGERweb query per zip prefix. These
tests pin its failure contract: fetch errors must propagate (so the wrapping
Prefect task retries instead of caching a truncated result), a prefix that
contributes zero ZCTAs must raise, and overlapping prefixes must be deduped.
"""
from __future__ import annotations

import geopandas as gpd
import pytest
import requests
from shapely.geometry import Point

import src.pipelines.tiger as tiger


def _zcta_chunk(zctas: list[str]) -> gpd.GeoDataFrame:
    """Build a chunk shaped like esri_geojson_to_gdf's TIGERweb ZCTA response."""
    return gpd.GeoDataFrame(
        {
            "ZCTA5": zctas,
            "GEOID": zctas,
            "NAME": [f"ZCTA5 {z}" for z in zctas],
        },
        geometry=[Point(-90.0, 35.0)] * len(zctas),
        crs="EPSG:4326",
    )


def _empty_chunk() -> gpd.GeoDataFrame:
    """Mirror esri_geojson_to_gdf's empty-features return."""
    return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs="EPSG:4326")


def _fake_fetch(
    monkeypatch: pytest.MonkeyPatch,
    pages_by_prefix: dict[str, list[gpd.GeoDataFrame] | Exception],
) -> None:
    """Route tiger's esri_geojson_to_gdf by zip prefix to canned pages.

    Each prefix maps to either an ordered list of pages (served by
    resultOffset; exhausted offsets return an empty chunk, ending pagination)
    or an Exception instance to raise on that prefix's first request.
    """
    def fake(url: str, params: dict) -> gpd.GeoDataFrame:
        # where clause is f"ZCTA5 LIKE '{prefix}%'"
        prefix = params["where"].split("'")[1].rstrip("%")
        result = pages_by_prefix[prefix]
        if isinstance(result, Exception):
            raise result
        page_index = params["resultOffset"] // params["resultRecordCount"]
        if page_index < len(result):
            return result[page_index].copy()
        return _empty_chunk()

    monkeypatch.setattr(tiger, "esri_geojson_to_gdf", fake)


def test_request_exception_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """A network failure on any prefix must raise, not return a truncated result.

    Regression: a swallowed ConnectionError on the '91' prefix silently dropped
    all 114 91xxx ZCTAs from los_angeles, and the "successful" truncated result
    was cached for 7 days because the Prefect task never saw a failure.
    """
    _fake_fetch(monkeypatch, {
        "90": [_zcta_chunk(["90001", "90002"])],
        "91": requests.exceptions.ConnectionError("connection reset by peer"),
    })

    with pytest.raises(requests.exceptions.ConnectionError):
        tiger.get_state_zctas(["90", "91"])


def test_empty_prefix_raises_value_error_naming_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured prefix contributing zero ZCTAs must fail loudly, named."""
    _fake_fetch(monkeypatch, {
        "90": [_zcta_chunk(["90001", "90002"])],
        "91": [],
    })

    with pytest.raises(ValueError, match="91"):
        tiger.get_state_zctas(["90", "91"])


def test_overlapping_prefixes_are_deduped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Overlapping prefixes (e.g. memphis '38' + '386') double-fetch the same
    ZCTAs; the function must return each ZCTA5CE exactly once."""
    _fake_fetch(monkeypatch, {
        "38": [_zcta_chunk(["38103", "38601"])],
        "386": [_zcta_chunk(["38601"])],
    })

    gdf = tiger.get_state_zctas(["38", "386"])

    assert sorted(gdf["ZCTA5CE"]) == ["38103", "38601"]


def test_pagination_concatenates_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """A full page (100 records) must trigger a fetch of the next offset."""
    page1 = _zcta_chunk([f"90{i:03d}" for i in range(100)])
    page2 = _zcta_chunk(["90100", "90101"])
    _fake_fetch(monkeypatch, {"90": [page1, page2]})

    gdf = tiger.get_state_zctas(["90"])

    assert len(gdf) == 102
    assert "ZCTA5CE" in gdf.columns
