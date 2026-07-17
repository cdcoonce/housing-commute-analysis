"""Tests for the final-dataset schema contract."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import polars as pl
import pytest

from src.pipelines.schema import REQUIRED_COLUMNS, validate_final_dataset

_FINAL_DIR = Path(__file__).resolve().parents[1] / "data" / "final"


@pytest.mark.parametrize("csv_path", sorted(_FINAL_DIR.glob("final_zcta_dataset_*.csv")))
def test_all_committed_datasets_pass_schema(csv_path: Path) -> None:
    validate_final_dataset(pl.read_csv(csv_path))


def test_validate_accepts_pipeline_output_dtypes(tmp_path: Path) -> None:
    """Regression: the pipeline validates its persisted CSV via pl.read_csv, NOT
    pl.from_pandas (which raises ImportError needing pyarrow for the real frame's
    Int64/categorical columns). Reproduce the pandas-output -> CSV -> read-back ->
    validate path on the exact mixed dtypes that broke the live run.
    """
    src = _FINAL_DIR / "final_zcta_dataset_phoenix.csv"
    pdf = pd.read_csv(src)
    # A categorical column (as build_metro_flow produces for income_segment) is
    # enough to make pl.from_pandas require pyarrow; confirm the read-back path
    # validates it fine without that dependency.
    pdf["income_segment"] = pdf["income_segment"].astype("category")
    assert str(pdf["income_segment"].dtype) == "category"
    out = tmp_path / "final_zcta_dataset_test.csv"
    pdf.to_csv(out, index=False)
    # The read-back path must validate without pyarrow.
    validate_final_dataset(pl.read_csv(out))


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


def test_duplicate_zcta_rejected() -> None:
    """One row per ZCTA is the dataset's core invariant; duplicated ZCTA5CE values
    (how a 76-row/52-unique memphis got committed) must fail validation loudly."""
    data = {c: [1.0, 1.0] for c in REQUIRED_COLUMNS}
    data["income_segment"] = ["Low", "Low"]
    data["ZCTA5CE"] = ["38103", "38103"]
    with pytest.raises(ValueError, match="ZCTA5CE.*duplicate"):
        validate_final_dataset(pl.DataFrame(data))


def test_unique_zcta_accepted() -> None:
    data = {c: [1.0, 1.0] for c in REQUIRED_COLUMNS}
    data["income_segment"] = ["Low", "High"]
    data["ZCTA5CE"] = ["38103", "38104"]
    validate_final_dataset(pl.DataFrame(data))
