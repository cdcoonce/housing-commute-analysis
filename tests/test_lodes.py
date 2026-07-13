"""Unit tests for src/pipelines/lodes.py (all offline)."""
from __future__ import annotations

import pytest

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
