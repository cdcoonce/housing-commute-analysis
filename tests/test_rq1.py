"""Tests for RQ1 housing-commute trade-off analysis (pure analyze half)."""
from __future__ import annotations

import polars as pl
import pytest

from src.models.results import RQ1Results
from src.models.rq1_housing_commute_tradeoff import analyze_rq1


def test_analyze_rq1_selects_lower_aic_model(sample_zcta_df: pl.DataFrame) -> None:
    result = analyze_rq1(sample_zcta_df)
    assert isinstance(result, RQ1Results)
    assert result.best_model_name in ("Linear", "Quadratic")
    aics = {"Linear": result.model_linear["aic"], "Quadratic": result.model_quad["aic"]}
    assert aics[result.best_model_name] == min(aics.values())


def test_analyze_rq1_output_shapes(sample_zcta_df: pl.DataFrame) -> None:
    result = analyze_rq1(sample_zcta_df)
    n = result.sample_size
    assert n > 0
    assert result.y_pred.shape == (n,)
    assert result.residuals.shape == (n,)
    assert result.cv_rmse_linear > 0
    assert "VIF" in result.vif_linear.columns


def test_analyze_rq1_missing_column_raises(sample_zcta_df: pl.DataFrame) -> None:
    df = sample_zcta_df.drop("renter_share")
    with pytest.raises(ValueError, match="Missing required columns"):
        analyze_rq1(df)


def test_analyze_rq1_includes_employment_features(sample_zcta_df) -> None:
    result = analyze_rq1(sample_zcta_df)
    for name in ("job_density", "distance_to_cbd_km", "job_accessibility"):
        assert name in result.feature_names
    # positional contract: stored names are ['const', ...]; commute stays at
    # index 1 and commute² at index 2, matching report_rq1's params/pvalues reads
    assert result.model_quad["feature_names"][1] == "commute_min_proxy"
    assert result.model_quad["feature_names"][2] == "commute_min_proxy²"


def test_analyze_rq1_missing_employment_column_raises(sample_zcta_df) -> None:
    with pytest.raises(ValueError, match="job_density"):
        analyze_rq1(sample_zcta_df.drop("job_density"))
