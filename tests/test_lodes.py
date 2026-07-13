"""Unit tests for src/pipelines/lodes.py (all offline)."""
from __future__ import annotations

import pytest
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon

import src.pipelines.lodes as lodes


def test_wac_url_pattern() -> None:
    assert lodes.wac_url("az", 2021) == (
        "https://lehd.ces.census.gov/data/lodes/LODES8/az/wac/az_wac_S000_JT00_2021.csv.gz"
    )


def test_xwalk_url_pattern() -> None:
    assert lodes.xwalk_url("tn") == (
        "https://lehd.ces.census.gov/data/lodes/LODES8/tn/tn_xwalk.csv.gz"
    )


def test_states_for_counties_memphis_tristate() -> None:
    """Memphis spans TN+MS+AR — all three states must be fetched or suburbs are lost."""
    counties = [("47", "157"), ("47", "047"), ("05", "035"), ("28", "033")]
    assert lodes.states_for_counties(counties) == ("ar", "ms", "tn")


def test_states_for_counties_unmapped_fips_raises() -> None:
    with pytest.raises(KeyError):
        lodes.states_for_counties([("99", "001")])


def _fake_http(monkeypatch, wac: pd.DataFrame, xwalk: pd.DataFrame) -> None:
    """Route lodes' http_csv_to_df by URL to synthetic WAC / crosswalk frames.

    Asserts the load-bearing read_csv kwargs (compression/usecols/dtype) that
    fetch_state_jobs must pass, so a future edit that drops one fails here
    instead of silently degrading the production reads.
    """
    def fake(url: str, timeout: int = 180, **kwargs):
        assert kwargs.get("compression") == "gzip", f"missing compression='gzip' for {url}"
        if "/wac/" in url:
            assert kwargs.get("usecols") == ["w_geocode", "C000"], f"wrong usecols for {url}"
            assert kwargs.get("dtype") == {"w_geocode": str}, f"wrong dtype for {url}"
            return wac.copy()
        assert kwargs.get("usecols") == ["tabblk2020", "zcta", "trct"], f"wrong usecols for {url}"
        assert kwargs.get("dtype") == {
            "tabblk2020": str, "zcta": str, "trct": str,
        }, f"wrong dtype for {url}"
        return xwalk.copy()
    monkeypatch.setattr(lodes, "http_csv_to_df", fake)


def test_fetch_state_jobs_aggregates_and_drops_unassigned(monkeypatch) -> None:
    wac = pd.DataFrame({
        "w_geocode": ["040130001001000", "040130001001001", "040130002002000",
                      "040130003003000", "040130004004000"],
        "C000": [10, 5, 7, 3, 9],
    })
    xwalk = pd.DataFrame({
        "tabblk2020": ["040130001001000", "040130001001001", "040130002002000",
                       "040130003003000", "040130004004000"],
        "zcta": ["85001", "85001", "85002", "", "99999"],  # blank + sentinel dropped
        "trct": ["04013000100", "04013000100", "04013000200",
                 "04013000300", "04013000400"],
    })
    _fake_http(monkeypatch, wac, xwalk)
    out = lodes.fetch_state_jobs("az", 2021)
    assert list(out.columns) == ["zcta", "trct", "jobs"]
    # blocks 1+2 aggregate into one (zcta, trct) pair
    row = out[(out["zcta"] == "85001") & (out["trct"] == "04013000100")]
    assert row["jobs"].item() == 15
    # blank-zcta and 99999-sentinel blocks are dropped entirely
    assert set(out["zcta"]) == {"85001", "85002"}


def test_fetch_metro_lodes_concats_states(monkeypatch) -> None:
    wac = pd.DataFrame({"w_geocode": ["1" * 15], "C000": [4]})
    xwalk = pd.DataFrame({
        "tabblk2020": ["1" * 15], "zcta": ["38103"], "trct": ["1" * 11],
    })
    _fake_http(monkeypatch, wac, xwalk)
    out = lodes.fetch_metro_lodes(("ar", "ms", "tn"), 2021)
    # one identical synthetic row per state, aggregated across the concat
    assert out["jobs"].sum() == 12


def test_zcta_job_counts_sums_tracts_and_zfills() -> None:
    lodes_df = pd.DataFrame({
        "zcta": ["85001", "85001", "8500"],  # "8500" exercises zfill
        "trct": ["04013000100", "04013000200", "04013000300"],
        "jobs": [15, 7, 3],
    })
    out = lodes.zcta_job_counts(lodes_df)
    assert list(out.columns) == ["ZCTA5CE", "job_count"]
    assert out.set_index("ZCTA5CE").loc["85001", "job_count"] == 22
    assert out.set_index("ZCTA5CE").loc["08500", "job_count"] == 3


def _square(cx: float, cy: float, half: float = 1000.0) -> Polygon:
    return Polygon([
        (cx - half, cy - half), (cx + half, cy - half),
        (cx + half, cy + half), (cx - half, cy + half),
    ])


def test_distance_to_cbd_km_zero_at_centroid_and_min_over_points() -> None:
    """Two 2km squares in UTM 12N, centroids 10km apart. A CBD point placed at
    each centroid (via inverse projection to lat/lon) must give ~0 km for both
    ZCTAs — proving both the centroid math and the min-over-points rule."""
    import pyproj

    utm = 32612
    c0, c1 = (400000.0, 3700000.0), (410000.0, 3700000.0)
    zctas = gpd.GeoDataFrame(
        {"ZCTA5CE": ["85001", "85002"]},
        geometry=[_square(*c0), _square(*c1)],
        crs=utm,
    )
    to_wgs = pyproj.Transformer.from_crs(utm, 4326, always_xy=True)
    lon0, lat0 = to_wgs.transform(*c0)
    lon1, lat1 = to_wgs.transform(*c1)

    # Single CBD at centroid 0: ZCTA 0 is ~0 km away, ZCTA 1 is ~10 km away
    single = lodes.distance_to_cbd_km(zctas, [(lat0, lon0)], utm)
    d = single.set_index("ZCTA5CE")["distance_to_cbd_km"]
    assert d["85001"] < 0.01
    assert abs(d["85002"] - 10.0) < 0.1

    # Dual CBD (DFW pattern): min over points → both ~0
    dual = lodes.distance_to_cbd_km(zctas, [(lat0, lon0), (lat1, lon1)], utm)
    d2 = dual.set_index("ZCTA5CE")["distance_to_cbd_km"]
    assert d2["85001"] < 0.01 and d2["85002"] < 0.01
