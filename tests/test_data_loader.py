"""Tests for src.models.data_loader module."""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from src.models.data_loader import PANEL_FILES, load_and_validate_data, load_panel_data


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


def _write_panel_csvs(final_dir: Path) -> None:
    """Write a minimal valid (zori, lodes, acs2019) panel trio for metro PHX.

    Includes a leading-zero ZCTA (08501) so round-trip tests can assert the
    loader pins ZCTA5CE to Utf8 instead of letting CSV inference eat the zero.
    """
    zctas = ["08501", "85004"]
    zori = pl.DataFrame({
        "ZCTA5CE": [z for z in zctas for _ in range(2)],
        "period": ["2019-01-31", "2019-02-28"] * 2,
        "zori": [1500.0, 1510.0, 1200.0, 1195.5],
    })
    lodes = pl.DataFrame({
        "ZCTA5CE": [z for z in zctas for _ in range(2)],
        "year": [2015, 2016] * 2,
        "job_count": [1000, 1050, 800, 790],
        "job_accessibility": [50_000.0, 51_000.0, 42_000.0, 41_500.0],
    })
    acs = pl.DataFrame({
        "ZCTA5CE": zctas,
        "commute_min_proxy_2019": [24.5, 31.2],
        "ttw_total_2019": [3200, 2100],
    })
    zori.write_csv(final_dir / "zori_panel_phoenix.csv")
    lodes.write_csv(final_dir / "lodes_panel_phoenix.csv")
    acs.write_csv(final_dir / "acs_commute_2019_phoenix.csv")


class TestLoadPanelData:
    """Tests for the load_panel_data function (RQ4 panel products)."""

    def test_panel_files_mapping(self) -> None:
        """PANEL_FILES pins the three panel product filename templates."""
        assert PANEL_FILES == {
            "zori": "zori_panel_{metro}.csv",
            "lodes": "lodes_panel_{metro}.csv",
            "acs2019": "acs_commute_2019_{metro}.csv",
        }

    def test_round_trip_pins_zcta_dtype(self, tmp_path: Path) -> None:
        """A leading-zero ZCTA written to CSV survives the loader as a string."""
        _write_panel_csvs(tmp_path)

        zori, lodes, acs = load_panel_data("PHX", tmp_path)

        for frame in (zori, lodes, acs):
            assert isinstance(frame, pl.DataFrame)
            assert frame["ZCTA5CE"].dtype == pl.Utf8
            assert "08501" in frame["ZCTA5CE"].to_list()

    def test_raises_on_invalid_panel(self, tmp_path: Path) -> None:
        """A panel failing its schema validator raises ValueError naming the file."""
        _write_panel_csvs(tmp_path)
        # Corrupt the zori panel: non-positive rent violates validate_zori_panel.
        bad = pl.DataFrame({
            "ZCTA5CE": ["08501"],
            "period": ["2019-01-31"],
            "zori": [-5.0],
        })
        bad.write_csv(tmp_path / "zori_panel_phoenix.csv")

        with pytest.raises(ValueError, match="zori_panel_phoenix.csv"):
            load_panel_data("PHX", tmp_path)

    def test_raises_on_missing_panel_file(self, tmp_path: Path) -> None:
        """An absent panel file raises FileNotFoundError (callers decide to skip)."""
        _write_panel_csvs(tmp_path)
        (tmp_path / "lodes_panel_phoenix.csv").unlink()

        with pytest.raises(FileNotFoundError, match="lodes_panel_phoenix.csv"):
            load_panel_data("PHX", tmp_path)

    def test_raises_on_invalid_metro(self, tmp_path: Path) -> None:
        """An unknown metro code raises ValueError before touching the filesystem."""
        with pytest.raises(ValueError, match="Invalid metro code"):
            load_panel_data("NYC", tmp_path)
