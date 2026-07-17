"""Unit tests for src/pipelines/tiger.py (all offline).

get_state_zctas fetches one paginated TIGERweb query per zip prefix. These
tests pin its failure contract: fetch errors must propagate (so the wrapping
Prefect task retries instead of caching a truncated result), a prefix that
contributes zero ZCTAs must raise, and overlapping prefixes must be deduped.

The CBSA layer tests pin the vintage-resolution contract (issue #2): the CBSA
layer id is resolved from the MapServer's layer listing by matching the pinned
vintage group (never a hardcoded index), a missing or ambiguous match raises
instead of falling back, and the resolution is cached per process.
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


# --- CBSA layer resolution by pinned vintage (issue #2) ---


def _layer(
    layer_id: int,
    name: str,
    parent: int,
    layer_type: str = "Feature Layer",
    sub: list[int] | None = None,
) -> dict:
    return {
        "id": layer_id,
        "name": name,
        "parentLayerId": parent,
        "type": layer_type,
        "subLayerIds": sub,
    }


def _cbsa_layer_listing() -> dict:
    """The real TIGERweb/CBSA/MapServer?f=json layer listing (probed 2026-07-17).

    This is the post-shuffle structure that broke the hardcoded index: an
    "ACS 2025" group was inserted at ids 5-10, so the ACS-2024-vintage
    "Metropolitan Statistical Areas" layer sits at id 15 and the
    Census-2020-vintage one moved to id 26.
    """
    return {
        "mapName": "CBSA",
        "layers": [
            _layer(0, "Combined Statistical Areas", -1),
            _layer(1, "Metropolitan and Micropolitan Statistical Areas", -1,
                   "Group Layer", [2, 3, 4]),
            _layer(2, "Metropolitan Divisions", 1),
            _layer(3, "Metropolitan Statistical Areas", 1),
            _layer(4, "Micropolitan Statistical Areas", 1),
            _layer(5, "ACS 2025", -1, "Group Layer", [6, 7]),
            _layer(6, "Combined Statistical Areas", 5),
            _layer(7, "Metropolitan and Micropolitan Statistical Areas", 5,
                   "Group Layer", [8, 9, 10]),
            _layer(8, "Metropolitan Divisions", 7),
            _layer(9, "Metropolitan Statistical Areas", 7),
            _layer(10, "Micropolitan Statistical Areas", 7),
            _layer(11, "ACS 2024", -1, "Group Layer", [12, 13]),
            _layer(12, "Combined Statistical Areas", 11),
            _layer(13, "Metropolitan and Micropolitan Statistical Areas", 11,
                   "Group Layer", [14, 15, 16]),
            _layer(14, "Metropolitan Divisions", 13),
            _layer(15, "Metropolitan Statistical Areas", 13),
            _layer(16, "Micropolitan Statistical Areas", 13),
            _layer(17, "Census 2020", -1, "Group Layer", [18, 19, 23, 24]),
            _layer(18, "Combined New England City and Town Areas", 17),
            _layer(19, "New England City and Town Areas", 17,
                   "Group Layer", [20, 21, 22]),
            _layer(20, "New England City and Town Area Divisions", 19),
            _layer(21, "Metropolitan New England City and Town Areas", 19),
            _layer(22, "Micropolitan New England City and Town Areas", 19),
            _layer(23, "Combined Statistical Areas", 17),
            _layer(24, "Metropolitan and Micropolitan Statistical Areas", 17,
                   "Group Layer", [25, 26, 27]),
            _layer(25, "Metropolitan Divisions", 24),
            _layer(26, "Metropolitan Statistical Areas", 24),
            _layer(27, "Micropolitan Statistical Areas", 24),
        ],
    }


def _fake_listing(
    monkeypatch: pytest.MonkeyPatch, listing: dict
) -> list[tuple[str, dict | None]]:
    """Serve `listing` as the MapServer layer-list JSON; record each fetch.

    Also resets the module-level resolution cache so tests are isolated
    (raising=False keeps this a no-op during the pre-implementation red phase).
    """
    calls: list[tuple[str, dict | None]] = []

    def fake(url: str, params: dict | None = None) -> dict:
        calls.append((url, params))
        return listing

    monkeypatch.setattr(tiger, "_cbsa_layer_cache", {}, raising=False)
    monkeypatch.setattr(tiger, "http_json_to_dict", fake, raising=False)
    return calls


def test_resolve_cbsa_layer_pins_acs_2024_vintage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pinned vintage (ACS 2024, 2023 OMB delineations) resolves to id 15.

    This is the vintage the committed 9-metro datasets were built against;
    the resolver makes it explicit instead of trusting index 15 to keep
    meaning the same thing.
    """
    _fake_listing(monkeypatch, _cbsa_layer_listing())

    assert tiger.CBSA_VINTAGE == "ACS 2024"
    assert tiger.resolve_cbsa_layer_id() == 15


def test_resolve_cbsa_layer_selects_by_vintage_not_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolution follows the vintage group, not layer position: the same
    listing yields the Census-2020 layer (id 26) when that vintage is asked
    for, proving a future TIGERweb reshuffle cannot silently swap vintages."""
    _fake_listing(monkeypatch, _cbsa_layer_listing())

    assert tiger.resolve_cbsa_layer_id(vintage="Census 2020") == 26


def test_resolve_missing_vintage_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A listing without the pinned vintage must raise, never fall back to an
    index — an unknown vintage means the service was reorganized under us."""
    listing = _cbsa_layer_listing()
    listing["layers"] = [
        layer for layer in listing["layers"]
        if layer["id"] not in {11, 12, 13, 14, 15, 16}
    ]
    _fake_listing(monkeypatch, listing)

    with pytest.raises(ValueError, match="ACS 2024"):
        tiger.resolve_cbsa_layer_id()


def test_resolve_ambiguous_match_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two Metropolitan Statistical Areas layers under the pinned vintage is
    ambiguous: refusing to guess beats silently picking the wrong polygon set."""
    listing = _cbsa_layer_listing()
    listing["layers"].append(_layer(28, "Metropolitan Statistical Areas", 13))
    _fake_listing(monkeypatch, listing)

    with pytest.raises(ValueError, match="ambiguous"):
        tiger.resolve_cbsa_layer_id()


def test_resolution_is_cached_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """The layer listing is fetched once per process, not once per metro."""
    calls = _fake_listing(monkeypatch, _cbsa_layer_listing())

    first = tiger.resolve_cbsa_layer_id()
    second = tiger.resolve_cbsa_layer_id()

    assert first == second == 15
    assert len(calls) == 1


def test_get_cbsa_polygon_queries_resolved_layer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_cbsa_polygon must query the resolved layer's /query endpoint with
    the same CBSA filter params as before (Prefect task inputs unchanged)."""
    _fake_listing(monkeypatch, _cbsa_layer_listing())
    captured: dict = {}

    def fake_query(url: str, params: dict) -> gpd.GeoDataFrame:
        captured["url"] = url
        captured["params"] = params
        return gpd.GeoDataFrame(
            {"CBSA": ["38060"], "NAME": ["Phoenix-Mesa-Chandler, AZ Metro Area"]},
            geometry=[Point(-112.07, 33.45)],
            crs="EPSG:4326",
        )

    monkeypatch.setattr(tiger, "esri_geojson_to_gdf", fake_query)

    gdf = tiger.get_cbsa_polygon("38060")

    assert captured["url"] == f"{tiger.TIGER_CBSA_BASE_URL}/15/query"
    assert captured["params"]["where"] == "CBSA='38060'"
    assert captured["params"]["outFields"] == "CBSA,NAME"
    assert gdf["CBSA"].iloc[0] == "38060"
