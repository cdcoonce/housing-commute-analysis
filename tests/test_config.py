"""Tests for metro configuration integrity in src/pipelines/config.py."""

from __future__ import annotations

import pytest

from src.pipelines.config import CENSUS_API_KEY, METRO_CONFIGS

REQUIRED_KEYS = {"cbsa_code", "counties", "zip_prefixes", "utm_zone", "name"}


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
