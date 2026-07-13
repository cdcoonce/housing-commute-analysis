"""Unit tests for src/pipelines/lodes.py (all offline)."""
from __future__ import annotations

import pytest
import pandas as pd

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
    """Route lodes' http_csv_to_df by URL to synthetic WAC / crosswalk frames."""
    def fake(url: str, timeout: int = 180, **kwargs):
        return wac.copy() if "/wac/" in url else xwalk.copy()
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
