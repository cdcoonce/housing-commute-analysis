"""Tests for RQ3 ACI analysis (pure analyze half)."""
from __future__ import annotations

import numpy as np
import polars as pl

from src.models.results import RQ3Results
from src.models.rq3_aci_analysis import analyze_rq3


def test_analyze_rq3_aci_is_sum_of_zscores(sample_zcta_df: pl.DataFrame) -> None:
    result = analyze_rq3(sample_zcta_df)
    assert isinstance(result, RQ3Results)
    df = result.df_with_aci
    assert df is not None
    rent = df["rent_to_income"]
    commute = df["commute_min_proxy"]
    rent_z = (rent - rent.mean()) / rent.std()        # polars std is sample (ddof=1)
    commute_z = (commute - commute.mean()) / commute.std()
    expected = (rent_z + commute_z).to_numpy()
    assert np.allclose(df["ACI"].to_numpy(), expected, rtol=1e-9, atol=1e-9)


def test_analyze_rq3_quantile_keys(sample_zcta_df: pl.DataFrame) -> None:
    result = analyze_rq3(sample_zcta_df)
    assert set(result.quantile_results.keys()).issubset({0.25, 0.5, 0.75})


def test_rq3_includes_employment_candidates(sample_zcta_df: pl.DataFrame) -> None:
    result = analyze_rq3(sample_zcta_df)
    for name in ("job_density", "distance_to_cbd_km", "job_accessibility"):
        assert name in result.feature_names


def test_rq3_still_runs_without_employment_columns(sample_zcta_df: pl.DataFrame) -> None:
    df = sample_zcta_df.drop(["job_density", "distance_to_cbd_km", "job_accessibility"])
    result = analyze_rq3(df)
    assert result.aci_model is not None
    assert 'job_density' not in result.feature_names
