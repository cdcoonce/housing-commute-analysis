"""Tests for the final-dataset schema contract."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import polars as pl
import pytest

from src.pipelines.schema import (
    REQUIRED_COLUMNS,
    validate_acs_commute_2019,
    validate_final_dataset,
    validate_lodes_panel,
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


# --- validate_lodes_panel (RQ4 LODES accessibility panel; design §1/§5) ---


def _valid_lodes_panel() -> pl.DataFrame:
    """Minimal valid panel: Utf8 zero-padded ZCTAs, in-window years, int counts."""
    return pl.DataFrame(
        {
            "ZCTA5CE": ["08501", "85001", "85001"],
            "year": [2015, 2015, 2016],
            "job_count": [0, 1200, 1250],
            "job_accessibility": [10.5, 50000.0, 51000.25],
        }
    )


def test_lodes_panel_valid_frame_passes() -> None:
    assert validate_lodes_panel(_valid_lodes_panel()) == []


def test_lodes_panel_wrong_columns_rejected() -> None:
    errors = validate_lodes_panel(_valid_lodes_panel().drop("job_count"))
    assert errors and any("columns" in e for e in errors)


def test_lodes_panel_duplicate_key_rejected() -> None:
    df = pl.DataFrame(
        {
            "ZCTA5CE": ["85001", "85001"],
            "year": [2015, 2015],
            "job_count": [10, 10],
            "job_accessibility": [1.0, 1.0],
        }
    )
    errors = validate_lodes_panel(df)
    assert errors and any("duplicate" in e for e in errors)


def test_lodes_panel_negative_job_count_rejected() -> None:
    df = _valid_lodes_panel().with_columns(
        pl.Series("job_count", [-1, 1200, 1250])
    )
    errors = validate_lodes_panel(df)
    assert errors and any("job_count" in e for e in errors)


def test_lodes_panel_float_job_count_rejected() -> None:
    """job_count must stay integer dtype — the gate byte-compares it (design §3)."""
    df = _valid_lodes_panel().with_columns(
        pl.Series("job_count", [0.0, 1200.0, 1250.0], dtype=pl.Float64)
    )
    errors = validate_lodes_panel(df)
    assert errors and any("integer" in e for e in errors)


def test_lodes_panel_year_outside_window_rejected() -> None:
    df = _valid_lodes_panel().with_columns(pl.Series("year", [2014, 2015, 2016]))
    errors = validate_lodes_panel(df)
    assert errors and any("year" in e for e in errors)


def test_lodes_panel_nonpositive_accessibility_rejected() -> None:
    """min(job_accessibility) > 0 protects the log transform (design §3 sanity)."""
    df = _valid_lodes_panel().with_columns(
        pl.Series("job_accessibility", [0.0, 50000.0, 51000.25])
    )
    errors = validate_lodes_panel(df)
    assert errors and any("job_accessibility" in e and "> 0" in e for e in errors)


def test_lodes_panel_null_accessibility_rejected() -> None:
    df = _valid_lodes_panel().with_columns(
        pl.Series("job_accessibility", [None, 50000.0, 51000.25], dtype=pl.Float64)
    )
    errors = validate_lodes_panel(df)
    assert errors and any("null" in e for e in errors)


def test_lodes_panel_i64_zcta_rejected() -> None:
    """A leading-zero ZCTA read without schema_overrides infers i64 — must fail."""
    df = _valid_lodes_panel().with_columns(pl.Series("ZCTA5CE", [8501, 85001, 85001]))
    errors = validate_lodes_panel(df)
    assert errors and any("Utf8" in e for e in errors)


def test_lodes_panel_non_5_digit_zcta_rejected() -> None:
    df = _valid_lodes_panel().with_columns(
        pl.Series("ZCTA5CE", ["8501", "85001", "85001"])
    )
    errors = validate_lodes_panel(df)
    assert errors and any("5-digit" in e for e in errors)


# --- validate_acs_commute_2019 (RQ4 frozen pre-COVID vintage; design §1/§5) ---


def _valid_acs_commute() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ZCTA5CE": ["08501", "85001"],
            "commute_min_proxy_2019": [24.5, 31.25],
            "ttw_total_2019": [1500, 2200],
        }
    )


def test_acs_commute_valid_frame_passes() -> None:
    assert validate_acs_commute_2019(_valid_acs_commute()) == []


def test_acs_commute_wrong_columns_rejected() -> None:
    errors = validate_acs_commute_2019(_valid_acs_commute().drop("ttw_total_2019"))
    assert errors and any("columns" in e for e in errors)


def test_acs_commute_duplicate_zcta_rejected() -> None:
    df = pl.DataFrame(
        {
            "ZCTA5CE": ["85001", "85001"],
            "commute_min_proxy_2019": [24.5, 24.5],
            "ttw_total_2019": [1500, 1500],
        }
    )
    errors = validate_acs_commute_2019(df)
    assert errors and any("duplicate" in e for e in errors)


def test_acs_commute_proxy_zero_rejected() -> None:
    """0 < commute_min_proxy_2019 < 180 is strict on both ends (design §3)."""
    df = _valid_acs_commute().with_columns(
        pl.Series("commute_min_proxy_2019", [0.0, 31.25])
    )
    errors = validate_acs_commute_2019(df)
    assert errors and any("commute_min_proxy_2019" in e for e in errors)


def test_acs_commute_proxy_180_rejected() -> None:
    df = _valid_acs_commute().with_columns(
        pl.Series("commute_min_proxy_2019", [24.5, 180.0])
    )
    errors = validate_acs_commute_2019(df)
    assert errors and any("commute_min_proxy_2019" in e for e in errors)


def test_acs_commute_null_proxy_rejected() -> None:
    """Zero-worker ZCTAs are dropped upstream — a null proxy must never land."""
    df = _valid_acs_commute().with_columns(
        pl.Series("commute_min_proxy_2019", [None, 31.25], dtype=pl.Float64)
    )
    errors = validate_acs_commute_2019(df)
    assert errors and any("null" in e for e in errors)


def test_acs_commute_nonpositive_ttw_total_rejected() -> None:
    """A non-null proxy with zero workers is arithmetically impossible upstream."""
    df = _valid_acs_commute().with_columns(pl.Series("ttw_total_2019", [0, 2200]))
    errors = validate_acs_commute_2019(df)
    assert errors and any("ttw_total_2019" in e for e in errors)


def test_acs_commute_i64_zcta_rejected() -> None:
    df = _valid_acs_commute().with_columns(pl.Series("ZCTA5CE", [8501, 85001]))
    errors = validate_acs_commute_2019(df)
    assert errors and any("Utf8" in e for e in errors)
