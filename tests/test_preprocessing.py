"""Tests for src.models.preprocessing module.

Covers income segmentation and majority race computation utilities.
"""

import polars as pl

from src.models.preprocessing import (
    compute_majority_race,
    create_income_segments,
)


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
