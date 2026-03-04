"""Tests for src.pipelines.acs module.

Covers compute_acs_features (derived feature engineering from raw ACS data)
and fetch_acs_for_county input validation.
"""

import pandas as pd
import pytest

from src.pipelines.acs import compute_acs_features, fetch_acs_for_county


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def raw_acs_df() -> pd.DataFrame:
    """Small DataFrame of realistic raw ACS data (4 rows) for compute_acs_features tests.

    Values are positive integers typical of census tract-level ACS estimates.
    """
    data = {
        "GEOID": ["04013100100", "04013100200", "04013100300", "04013100400"],
        "year": [2021, 2021, 2021, 2021],
        "median_rent": [1200, 950, 1500, 1100],
        "median_income": [60000, 45000, 80000, 55000],
        # Travel time to work bins (workers counts)
        "ttw_total": [500, 400, 600, 350],
        "ttw_lt5": [20, 15, 10, 25],
        "ttw_5_9": [30, 25, 20, 30],
        "ttw_10_14": [50, 40, 30, 35],
        "ttw_15_19": [60, 50, 50, 40],
        "ttw_20_24": [80, 60, 70, 50],
        "ttw_25_29": [50, 40, 60, 30],
        "ttw_30_34": [70, 55, 80, 45],
        "ttw_35_39": [40, 30, 50, 25],
        "ttw_40_44": [30, 25, 40, 20],
        "ttw_45_59": [40, 30, 80, 25],
        "ttw_60_89": [20, 20, 70, 15],
        "ttw_90_plus": [10, 10, 40, 10],
        # Mode of transportation
        "mode_total": [500, 400, 600, 350],
        "mode_car_alone": [350, 280, 360, 250],
        "mode_carpool": [50, 40, 60, 30],
        "mode_transit": [30, 25, 80, 20],
        "mode_walk": [20, 15, 30, 15],
        "mode_other": [10, 10, 20, 10],
        "mode_wfh": [40, 30, 50, 25],
        # Rent burden
        "rent_burden_total": [200, 180, 250, 150],
        "rent_burden_30_34": [30, 25, 35, 20],
        "rent_burden_35_39": [20, 18, 25, 15],
        "rent_burden_40_49": [25, 20, 30, 18],
        "rent_burden_50_plus": [35, 30, 50, 25],
        # Tenure
        "tenure_total": [400, 350, 500, 300],
        "tenure_owner": [240, 200, 280, 170],
        "tenure_renter": [160, 150, 220, 130],
        # Vehicles
        "vehicles_total": [400, 350, 500, 300],
        "vehicles_none": [20, 15, 40, 10],
        "vehicles_1": [150, 130, 180, 110],
        "vehicles_2_plus": [230, 205, 280, 180],
    }
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# compute_acs_features
# ---------------------------------------------------------------------------


class TestComputeAcsFeatures:
    """Tests for the compute_acs_features function."""

    def test_compute_acs_features_commute_proxy(
        self, raw_acs_df: pd.DataFrame
    ) -> None:
        """commute_min_proxy should be a weighted average in the plausible range [0, 90]."""
        result = compute_acs_features(raw_acs_df)

        assert "commute_min_proxy" in result.columns
        for value in result["commute_min_proxy"]:
            assert 0 <= value <= 90, (
                f"commute_min_proxy {value} outside plausible range [0, 90]"
            )

    def test_compute_acs_features_rent_to_income(
        self, raw_acs_df: pd.DataFrame
    ) -> None:
        """rent_to_income should equal median_rent / (median_income / 12)."""
        result = compute_acs_features(raw_acs_df)

        assert "rent_to_income" in result.columns
        for _, row in result.iterrows():
            expected = row["median_rent"] / (row["median_income"] / 12.0)
            assert row["rent_to_income"] == pytest.approx(expected, rel=1e-9)

    def test_compute_acs_features_mode_shares_sum(
        self, raw_acs_df: pd.DataFrame
    ) -> None:
        """Mode share percentages should approximately sum to 100 when all modes are included."""
        result = compute_acs_features(raw_acs_df)

        mode_cols = [
            "pct_drive_alone",
            "pct_carpool",
            "pct_transit",
            "pct_walk",
            "pct_wfh",
        ]
        for _, row in result.iterrows():
            # mode_other is not given its own pct column, so the five named
            # shares will sum to less than 100 by the "other" proportion.
            mode_sum = sum(row[col] for col in mode_cols)
            other_pct = (row["mode_other"] / row["mode_total"]) * 100
            assert mode_sum + other_pct == pytest.approx(100.0, abs=0.01)

    def test_compute_acs_features_negative_handled(
        self, raw_acs_df: pd.DataFrame
    ) -> None:
        """Census null codes (negative values) should be replaced with NaN."""
        df = raw_acs_df.copy()
        # Inject Census null codes into the first row
        df.loc[0, "median_rent"] = -666666666
        df.loc[0, "median_income"] = -666666666

        result = compute_acs_features(df)

        assert pd.isna(result.loc[0, "median_rent"])
        assert pd.isna(result.loc[0, "median_income"])
        assert pd.isna(result.loc[0, "rent_to_income"])

    def test_compute_acs_features_pct_car_sum(
        self, raw_acs_df: pd.DataFrame
    ) -> None:
        """pct_car should equal pct_drive_alone + pct_carpool."""
        result = compute_acs_features(raw_acs_df)

        for _, row in result.iterrows():
            expected = row["pct_drive_alone"] + row["pct_carpool"]
            assert row["pct_car"] == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# fetch_acs_for_county — input validation
# ---------------------------------------------------------------------------


class TestFetchAcsValidation:
    """Tests for fetch_acs_for_county input validation."""

    def test_fetch_acs_invalid_fips(self) -> None:
        """Non-numeric or wrong-length state FIPS should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid state FIPS"):
            fetch_acs_for_county(state_fips="X", county_fips="013", year=2021)

    def test_fetch_acs_invalid_year(self) -> None:
        """A year not in AVAILABLE_ACS_YEARS should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid ACS year"):
            fetch_acs_for_county(state_fips="04", county_fips="013", year=2020)
