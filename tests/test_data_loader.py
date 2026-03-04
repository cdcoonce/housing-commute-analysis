"""Tests for src.models.data_loader module."""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from src.models.data_loader import load_and_validate_data


class TestLoadAndValidateData:
    """Tests for the load_and_validate_data function."""

    def test_load_and_validate_data_valid(
        self, sample_zcta_csv: Path, sample_zcta_df: pl.DataFrame
    ) -> None:
        """Loading a valid CSV with a valid metro code returns a DataFrame with the expected shape."""
        result = load_and_validate_data(sample_zcta_csv, metro="PHX")

        assert isinstance(result, pl.DataFrame)
        assert result.shape[0] == sample_zcta_df.shape[0]
        assert result.shape[1] == sample_zcta_df.shape[1]

    def test_load_and_validate_data_invalid_metro(
        self, sample_zcta_csv: Path
    ) -> None:
        """Passing an invalid metro code raises ValueError."""
        with pytest.raises(ValueError, match="Invalid metro code"):
            load_and_validate_data(sample_zcta_csv, metro="NYC")

    def test_load_and_validate_data_missing_file(self, tmp_path: Path) -> None:
        """Passing a path that does not exist raises FileNotFoundError."""
        missing = tmp_path / "nonexistent.csv"

        with pytest.raises(FileNotFoundError, match="CSV file not found"):
            load_and_validate_data(missing, metro="PHX")

    def test_load_and_validate_data_drops_nulls(
        self, sample_zcta_df: pl.DataFrame, tmp_path: Path
    ) -> None:
        """Rows with null values in critical columns are dropped from the result."""
        # Inject nulls into two rows for a critical column
        modified = sample_zcta_df.with_columns(
            pl.when(pl.col("ZCTA5CE").is_in(["85000", "85001"]))
            .then(None)
            .otherwise(pl.col("rent_to_income"))
            .alias("rent_to_income")
        )
        csv_path = tmp_path / "nulls.csv"
        modified.write_csv(csv_path)

        result = load_and_validate_data(csv_path, metro="PHX")

        assert result.shape[0] == sample_zcta_df.shape[0] - 2

    def test_load_and_validate_data_missing_cols(self, tmp_path: Path) -> None:
        """A CSV missing critical columns raises ValueError."""
        incomplete = pl.DataFrame({
            "ZCTA5CE": ["85000"],
            "median_income": [50000.0],
        })
        csv_path = tmp_path / "incomplete.csv"
        incomplete.write_csv(csv_path)

        with pytest.raises(ValueError, match="Missing critical columns"):
            load_and_validate_data(csv_path, metro="PHX")
