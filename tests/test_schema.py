"""Tests for the final-dataset schema contract."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import polars as pl
import pytest

from src.pipelines.schema import (
    REQUIRED_COLUMNS,
    validate_final_dataset,
    validate_zori_panel,
)

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


# --- validate_zori_panel (RQ4 panel products; additive, design §1/§5) ---


def _valid_zori_panel() -> pl.DataFrame:
    """Minimal valid panel: Utf8 zero-padded ZCTAs, month-end periods, positive zori."""
    return pl.DataFrame(
        {
            "ZCTA5CE": ["08501", "85001", "85001"],
            "period": ["2020-01-31", "2020-01-31", "2020-02-29"],
            "zori": [1450.0, 1500.5, 1510.25],
        }
    )


def test_zori_panel_valid_frame_passes() -> None:
    assert validate_zori_panel(_valid_zori_panel()) == []


def test_zori_panel_wrong_columns_rejected() -> None:
    errors = validate_zori_panel(_valid_zori_panel().drop("zori"))
    assert errors and any("columns" in e for e in errors)


def test_zori_panel_null_zori_rejected() -> None:
    """Missing cells must be absent rows, never nulls (design §1 invariant)."""
    df = _valid_zori_panel().with_columns(
        pl.Series("zori", [None, 1500.5, 1510.25], dtype=pl.Float64)
    )
    errors = validate_zori_panel(df)
    assert errors and any("null" in e for e in errors)


def test_zori_panel_nonpositive_zori_rejected() -> None:
    df = _valid_zori_panel().with_columns(
        pl.Series("zori", [0.0, 1500.5, 1510.25], dtype=pl.Float64)
    )
    errors = validate_zori_panel(df)
    assert errors and any("zori" in e and "> 0" in e for e in errors)


def test_zori_panel_duplicate_key_rejected() -> None:
    df = pl.DataFrame(
        {
            "ZCTA5CE": ["85001", "85001"],
            "period": ["2020-01-31", "2020-01-31"],
            "zori": [1500.5, 1500.5],
        }
    )
    errors = validate_zori_panel(df)
    assert errors and any("duplicate" in e for e in errors)


def test_zori_panel_bad_date_rejected() -> None:
    df = _valid_zori_panel().with_columns(
        pl.Series("period", ["2020-13-99", "2020-01-31", "2020-02-29"])
    )
    errors = validate_zori_panel(df)
    assert errors and any("period" in e for e in errors)


def test_zori_panel_non_month_end_date_rejected() -> None:
    """Periods are exactly Zillow's month-end column labels (design §1)."""
    df = _valid_zori_panel().with_columns(
        pl.Series("period", ["2020-01-15", "2020-01-31", "2020-02-29"])
    )
    errors = validate_zori_panel(df)
    assert errors and any("month-end" in e for e in errors)


def test_zori_panel_i64_zcta_rejected() -> None:
    """A leading-zero ZCTA read without schema_overrides infers i64 — must fail."""
    df = _valid_zori_panel().with_columns(pl.Series("ZCTA5CE", [8501, 85001, 85001]))
    errors = validate_zori_panel(df)
    assert errors and any("Utf8" in e for e in errors)


def test_zori_panel_non_5_digit_zcta_rejected() -> None:
    df = _valid_zori_panel().with_columns(pl.Series("ZCTA5CE", ["8501", "85001", "85001"]))
    errors = validate_zori_panel(df)
    assert errors and any("5-digit" in e for e in errors)
