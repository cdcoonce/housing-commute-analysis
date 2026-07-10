"""Tests for the final-dataset schema contract."""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from src.pipelines.schema import REQUIRED_COLUMNS, validate_final_dataset

_FINAL_DIR = Path(__file__).resolve().parents[1] / "data" / "final"


@pytest.mark.parametrize("csv_path", sorted(_FINAL_DIR.glob("final_zcta_dataset_*.csv")))
def test_all_committed_datasets_pass_schema(csv_path: Path) -> None:
    validate_final_dataset(pl.read_csv(csv_path))


def test_missing_column_rejected() -> None:
    df = pl.DataFrame({c: [0.0] for c in REQUIRED_COLUMNS}).drop("zori")
    with pytest.raises(ValueError, match="missing columns"):
        validate_final_dataset(df)


def test_percent_out_of_range_rejected() -> None:
    data = {c: [1.0] for c in REQUIRED_COLUMNS}
    data["income_segment"] = ["Low"]
    data["pct_transit"] = [250.0]
    with pytest.raises(ValueError, match="out of range"):
        validate_final_dataset(pl.DataFrame(data))
