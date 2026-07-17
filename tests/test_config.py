"""Tests for metro configuration integrity in src/pipelines/config.py."""

from __future__ import annotations

import pytest

from src.pipelines.config import CENSUS_API_KEY, METRO_CONFIGS

REQUIRED_KEYS = {"cbsa_code", "counties", "zip_prefixes", "utm_zone", "name", "cbd_points"}


def test_all_metros_have_required_keys() -> None:
    """Every metro config must contain cbsa_code, counties, zip_prefixes, utm_zone, and name."""
    for metro, cfg in METRO_CONFIGS.items():
        missing = REQUIRED_KEYS - cfg.keys()
        assert not missing, f"Metro '{metro}' is missing keys: {missing}"


def test_no_duplicate_county_fips() -> None:
    """No metro should list the same (state_fips, county_fips) pair more than once."""
    for metro, cfg in METRO_CONFIGS.items():
        counties = cfg["counties"]
        assert len(counties) == len(set(counties)), (
            f"Metro '{metro}' has duplicate county FIPS entries"
        )


def test_cbsa_codes_are_valid() -> None:
    """All CBSA codes must be exactly five digits."""
    for metro, cfg in METRO_CONFIGS.items():
        code = cfg["cbsa_code"]
        assert isinstance(code, str) and len(code) == 5 and code.isdigit(), (
            f"Metro '{metro}' has invalid CBSA code: {code!r}"
        )


def test_utm_zones_are_valid_epsg() -> None:
    """All utm_zone values must be EPSG codes >= 32601 (UTM Zone 1N)."""
    for metro, cfg in METRO_CONFIGS.items():
        utm = cfg["utm_zone"]
        assert isinstance(utm, int) and utm >= 32601, (
            f"Metro '{metro}' has invalid UTM zone EPSG: {utm}"
        )


@pytest.mark.skipif(not CENSUS_API_KEY, reason="No .env")
def test_census_api_key_loaded() -> None:
    """CENSUS_API_KEY should be a non-empty string when the environment is configured."""
    assert CENSUS_API_KEY is not None
    assert len(CENSUS_API_KEY) > 0


def test_all_metros_have_plausible_cbd_points() -> None:
    """Every metro needs >=1 (lat, lon) CBD point inside the continental US."""
    for metro, cfg in METRO_CONFIGS.items():
        points = cfg["cbd_points"]
        assert isinstance(points, list) and len(points) >= 1, (
            f"Metro '{metro}' has no cbd_points"
        )
        for lat, lon in points:
            assert 24.0 < lat < 49.0, f"Metro '{metro}' CBD lat out of CONUS range: {lat}"
            assert -125.0 < lon < -66.0, f"Metro '{metro}' CBD lon out of CONUS range: {lon}"


def test_dallas_is_dual_cbd() -> None:
    """DFW is functionally dual-CBD: Dallas and Fort Worth, ~50 km apart."""
    assert len(METRO_CONFIGS["dallas"]["cbd_points"]) == 2


def test_zip_prefixes_are_non_overlapping() -> None:
    """No metro may list a zip prefix that is a prefix of another of its own prefixes.

    A shorter prefix already matches every ZCTA of any longer prefix it starts
    (e.g. "38" covers all of "386"), so listing both fetches those ZCTAs twice
    and duplicates every downstream row (root cause of memphis's duplicated rows).
    """
    for metro, cfg in METRO_CONFIGS.items():
        prefixes = cfg["zip_prefixes"]
        shadowed = [
            (a, b)
            for i, a in enumerate(prefixes)
            for j, b in enumerate(prefixes)
            if i != j and b.startswith(a)
        ]
        assert not shadowed, (
            f"Metro '{metro}' has overlapping zip_prefixes {shadowed}: the first "
            "prefix of each pair already covers the second, double-fetching those ZCTAs"
        )
