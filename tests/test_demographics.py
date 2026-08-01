"""Tests for src.pipelines.demographics module.

Covers demographic percentage computation and FIPS validation
in fetch_demographics_for_county.
"""

import numpy as np
import pandas as pd
import pytest

from src.pipelines.demographics import (
    aggregate_demographics_to_zcta,
    compute_demographic_percentages,
    fetch_demographics_for_county,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def demographics_df() -> pd.DataFrame:
    """Small DataFrame with realistic tract-level demographic counts.

    Three tracts with varied demographic compositions, plus one
    zero-population tract for edge-case testing.
    """
    return pd.DataFrame({
        "GEOID": ["04013100100", "04013100200", "04013100300", "04013100400"],
        "year": [2023, 2023, 2023, 2023],
        "total_pop": [5000, 3200, 8100, 0],
        "hispanic": [1500, 800, 2400, 0],
        "white_nh": [2000, 1200, 3000, 0],
        "black_nh": [700, 600, 1200, 0],
        "asian_nh": [500, 400, 1000, 0],
        "other_nh": [300, 200, 500, 0],
        "median_income": [55000, 42000, 78000, None],
    })


# ---------------------------------------------------------------------------
# compute_demographic_percentages
# ---------------------------------------------------------------------------


class TestComputeDemographicPercentages:
    """Tests for the compute_demographic_percentages function."""

    def test_compute_demographic_percentages(
        self, demographics_df: pd.DataFrame
    ) -> None:
        """Percentage columns should sum to approximately 100 for rows with nonzero total_pop."""
        result = compute_demographic_percentages(demographics_df)

        pct_cols = ["pct_hispanic", "pct_white", "pct_black", "pct_asian", "pct_other"]

        # Verify all percentage columns are present
        for col in pct_cols:
            assert col in result.columns

        # For rows with nonzero population, percentages should sum to ~100
        nonzero_mask = result["total_pop"] > 0
        pct_sums = result.loc[nonzero_mask, pct_cols].sum(axis=1)

        for row_sum in pct_sums:
            assert row_sum == pytest.approx(100.0, abs=1e-10)

    def test_compute_demographic_percentages_zero_pop(
        self, demographics_df: pd.DataFrame
    ) -> None:
        """Zero-population tracts should produce 0% for all groups without division errors."""
        result = compute_demographic_percentages(demographics_df)

        pct_cols = ["pct_hispanic", "pct_white", "pct_black", "pct_asian", "pct_other"]

        # The last row has total_pop == 0
        zero_pop_row = result.loc[result["total_pop"] == 0]
        assert len(zero_pop_row) == 1

        for col in pct_cols:
            assert zero_pop_row[col].iloc[0] == 0.0


# ---------------------------------------------------------------------------
# aggregate_demographics_to_zcta
# ---------------------------------------------------------------------------


def _tract_to_zcta(geoids: list[str], zcta: str = "85001") -> pd.DataFrame:
    """Map every tract in geoids to a single ZCTA."""
    return pd.DataFrame({"GEOID": geoids, "ZCTA5CE": [zcta] * len(geoids)})


def _demo_rows(geoids: list[str], total_pop: list[int], median_income: list[float]) -> pd.DataFrame:
    """Minimal tract-level demographics input for aggregate_demographics_to_zcta.

    pct_* columns are filled with 0 since these tests target median_income only.
    """
    n = len(geoids)
    return pd.DataFrame({
        "GEOID": geoids,
        "total_pop": total_pop,
        "pct_hispanic": [0.0] * n,
        "pct_white": [0.0] * n,
        "pct_black": [0.0] * n,
        "pct_asian": [0.0] * n,
        "pct_other": [0.0] * n,
        "median_income": median_income,
    })


class TestAggregateDemographicsToZcta:
    """Tests for population-weighted median_income aggregation (issue #80)."""

    def test_null_median_income_excluded_from_denominator(self) -> None:
        """A NaN median_income tract must not dilute the weighted mean."""
        geoids = ["04013100100", "04013100200"]
        demo = _demo_rows(geoids, total_pop=[1000, 1000], median_income=[100000.0, np.nan])
        tract_map = _tract_to_zcta(geoids)

        result = aggregate_demographics_to_zcta(demo, tract_map)

        assert result["median_income"].iloc[0] == 100000.0

    def test_sentinel_median_income_excluded(self) -> None:
        """Census suppression sentinel -666666666 must not corrupt the weighted mean."""
        geoids = ["04013100100", "04013100200"]
        demo = _demo_rows(geoids, total_pop=[1000, 1000], median_income=[100000.0, -666666666])
        tract_map = _tract_to_zcta(geoids)

        result = aggregate_demographics_to_zcta(demo, tract_map)

        assert result["median_income"].iloc[0] == 100000.0

    def test_all_null_median_income_yields_nan(self) -> None:
        """A ZCTA with no valid median_income observations should be NaN, not 0."""
        geoids = ["04013100100", "04013100200"]
        demo = _demo_rows(geoids, total_pop=[1000, 1000], median_income=[np.nan, -666666666])
        tract_map = _tract_to_zcta(geoids)

        result = aggregate_demographics_to_zcta(demo, tract_map)

        assert pd.isna(result["median_income"].iloc[0])

    def test_pct_hispanic_weighted_mean_unaffected(self) -> None:
        """Percentage weighting is unchanged: null-handling is scoped to median_income only."""
        geoids = ["04013100100", "04013100200"]
        demo = _demo_rows(geoids, total_pop=[1000, 3000], median_income=[50000.0, 50000.0])
        demo["pct_hispanic"] = [20.0, 60.0]
        tract_map = _tract_to_zcta(geoids)

        result = aggregate_demographics_to_zcta(demo, tract_map)

        assert result["pct_hispanic"].iloc[0] == 50.0

    def test_pct_hispanic_zero_pop_fallback_unchanged(self) -> None:
        """A ZCTA whose total_pop sums to 0 keeps the pre-existing 0.0 fallback."""
        geoids = ["04013100100", "04013100200"]
        demo = _demo_rows(geoids, total_pop=[0, 0], median_income=[50000.0, 50000.0])
        demo["pct_hispanic"] = [20.0, 60.0]
        tract_map = _tract_to_zcta(geoids)

        result = aggregate_demographics_to_zcta(demo, tract_map)

        assert result["pct_hispanic"].iloc[0] == 0.0


# ---------------------------------------------------------------------------
# fetch_demographics_for_county — FIPS validation
# ---------------------------------------------------------------------------


class TestFetchDemographicsInvalidFips:
    """Tests for FIPS validation in fetch_demographics_for_county."""

    def test_fetch_demographics_invalid_fips(self) -> None:
        """Non-numeric FIPS codes like 'X' should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid state_fips"):
            fetch_demographics_for_county(state_fips="X", county_fips="013")

        with pytest.raises(ValueError, match="Invalid county_fips"):
            fetch_demographics_for_county(state_fips="04", county_fips="X")
