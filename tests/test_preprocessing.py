"""Tests for src.models.preprocessing module.

Covers z-score standardization, feature standardization, income segmentation,
and majority race computation utilities.
"""

import logging

import polars as pl
import pytest

from src.models.preprocessing import (
    compute_majority_race,
    create_income_segments,
    standardize_features,
    zscore,
)


# ---------------------------------------------------------------------------
# zscore
# ---------------------------------------------------------------------------


class TestZscore:
    """Tests for the zscore helper function."""

    def test_zscore_mean_zero_std_one(self) -> None:
        """Z-scored series should have mean approximately 0 and std approximately 1."""
        series = pl.Series("vals", [10.0, 20.0, 30.0, 40.0, 50.0])
        result = zscore(series)

        assert result.mean() == pytest.approx(0.0, abs=1e-10)
        assert result.std() == pytest.approx(1.0, abs=1e-10)

    def test_zscore_constant_series(self) -> None:
        """A constant series (zero variance) should return all zeros."""
        series = pl.Series("const", [7.0, 7.0, 7.0, 7.0])
        result = zscore(series)

        assert result.to_list() == [0.0, 0.0, 0.0, 0.0]

    def test_zscore_empty_series(self) -> None:
        """An empty series should be handled without raising an exception."""
        series = pl.Series("empty", [], dtype=pl.Float64)
        result = zscore(series)

        assert len(result) == 0


# ---------------------------------------------------------------------------
# standardize_features
# ---------------------------------------------------------------------------


class TestStandardizeFeatures:
    """Tests for the standardize_features function."""

    def test_standardize_features_creates_z_cols(
        self, sample_zcta_df: pl.DataFrame
    ) -> None:
        """Standardization should add new columns with '_z' suffix."""
        features = ["median_income", "median_rent"]
        result = standardize_features(sample_zcta_df, features)

        assert "median_income_z" in result.columns
        assert "median_rent_z" in result.columns

    def test_standardize_features_preserves_originals(
        self, sample_zcta_df: pl.DataFrame
    ) -> None:
        """Original columns should remain unchanged after standardization."""
        features = ["median_income"]
        original_values = sample_zcta_df["median_income"].to_list()
        result = standardize_features(sample_zcta_df, features)

        assert result["median_income"].to_list() == original_values

    def test_standardize_features_empty_list(
        self, sample_zcta_df: pl.DataFrame
    ) -> None:
        """An empty features list should raise ValueError."""
        with pytest.raises(ValueError, match="Features list cannot be empty"):
            standardize_features(sample_zcta_df, [])

    def test_standardize_features_missing_column(
        self, sample_zcta_df: pl.DataFrame, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A feature not present in the DataFrame should be skipped with a warning."""
        with caplog.at_level(logging.WARNING):
            result = standardize_features(
                sample_zcta_df, ["nonexistent_column", "median_income"]
            )

        assert "nonexistent_column" in caplog.text
        assert "median_income_z" in result.columns
        assert "nonexistent_column_z" not in result.columns

    def test_standardize_features_zero_variance(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A feature with zero variance should be skipped with a warning logged."""
        df = pl.DataFrame({
            "constant": [5.0, 5.0, 5.0, 5.0],
            "varied": [1.0, 2.0, 3.0, 4.0],
        })

        with caplog.at_level(logging.WARNING):
            result = standardize_features(df, ["constant", "varied"])

        assert "constant" in caplog.text
        assert "constant_z" not in result.columns
        assert "varied_z" in result.columns


# ---------------------------------------------------------------------------
# create_income_segments
# ---------------------------------------------------------------------------


class TestCreateIncomeSegments:
    """Tests for the create_income_segments function."""

    def test_create_income_segments_terciles(
        self, sample_zcta_df: pl.DataFrame
    ) -> None:
        """Income segments should split data into roughly equal Low/Medium/High groups."""
        result = create_income_segments(sample_zcta_df)

        assert "income_segment" in result.columns

        counts = result["income_segment"].value_counts()
        segment_map = dict(
            zip(
                counts["income_segment"].to_list(),
                counts["count"].to_list(),
            )
        )

        for segment in ("Low", "Medium", "High"):
            assert segment in segment_map, f"Missing segment: {segment}"
            # Each tercile should contain roughly a third of the 20 rows
            assert segment_map[segment] >= 1

    def test_create_income_segments_already_exists(
        self, sample_zcta_df: pl.DataFrame
    ) -> None:
        """If the segment column already exists the DataFrame should be returned unchanged."""
        df_with_seg = sample_zcta_df.with_columns(
            pl.lit("Existing").alias("income_segment")
        )
        result = create_income_segments(df_with_seg)

        assert result["income_segment"].to_list() == ["Existing"] * len(df_with_seg)

    def test_create_income_segments_missing_income(
        self, sample_zcta_df: pl.DataFrame
    ) -> None:
        """If the income column is missing the DataFrame should be returned unchanged."""
        df_no_income = sample_zcta_df.drop("median_income")
        result = create_income_segments(df_no_income)

        assert "income_segment" not in result.columns


# ---------------------------------------------------------------------------
# compute_majority_race
# ---------------------------------------------------------------------------


class TestComputeMajorityRace:
    """Tests for the compute_majority_race function."""

    def test_compute_majority_race_assigns_max(self) -> None:
        """Each row should be labeled with the race column that has the highest percentage."""
        df = pl.DataFrame({
            "pct_white": [0.6, 0.1, 0.2],
            "pct_black": [0.2, 0.5, 0.1],
            "pct_hispanic": [0.1, 0.3, 0.6],
            "pct_asian": [0.1, 0.1, 0.1],
        })
        result = compute_majority_race(df)

        assert "majority_race" in result.columns
        assert result["majority_race"].to_list() == ["White", "Black", "Hispanic"]

    def test_compute_majority_race_handles_nulls(self) -> None:
        """Null values in race columns should be treated as 0.0."""
        df = pl.DataFrame({
            "pct_white": [None, 0.3],
            "pct_black": [0.4, None],
            "pct_hispanic": [0.1, 0.2],
            "pct_asian": [0.1, 0.1],
        })
        result = compute_majority_race(df)

        assert "majority_race" in result.columns
        # Row 0: nulls become 0.0, so Black (0.4) wins
        # Row 1: nulls become 0.0, so White (0.3) wins
        assert result["majority_race"].to_list() == ["Black", "White"]

    def test_compute_majority_race_insufficient_cols(self) -> None:
        """If fewer than 2 race columns are present the DataFrame should be returned unchanged."""
        df = pl.DataFrame({
            "pct_white": [0.5, 0.6],
            "other_col": [1, 2],
        })
        result = compute_majority_race(df)

        assert "majority_race" not in result.columns
        assert result.shape == df.shape
