"""Tests for RQ2 equity analysis (pure analyze half)."""
from __future__ import annotations

import numpy as np
import polars as pl

from src.models.results import ANOVAResult, RQ2Results
from src.models.rq2_equity_analysis import analyze_rq2


def test_analyze_rq2_returns_results(sample_zcta_df: pl.DataFrame) -> None:
    result = analyze_rq2(sample_zcta_df)
    assert isinstance(result, RQ2Results)
    assert isinstance(result.anova_results, list)
    for a in result.anova_results:
        assert isinstance(a, ANOVAResult)


def test_analyze_rq2_cluster_labels_bounded(sample_zcta_df: pl.DataFrame) -> None:
    result = analyze_rq2(sample_zcta_df)
    if result.cluster_labels is not None:
        assert 0 < len(result.cluster_labels) <= sample_zcta_df.height
        assert set(np.unique(result.cluster_labels)).issubset({0, 1, 2, 3})


def test_analyze_rq2_is_deterministic(sample_zcta_df: pl.DataFrame) -> None:
    r1 = analyze_rq2(sample_zcta_df)
    r2 = analyze_rq2(sample_zcta_df)
    if r1.cluster_labels is not None and r2.cluster_labels is not None:
        assert np.array_equal(r1.cluster_labels, r2.cluster_labels)


def test_rq2_interaction_includes_employment_controls(sample_zcta_df) -> None:
    result = analyze_rq2(sample_zcta_df)
    names = result.interaction_model['feature_names']
    for name in ("job_density", "distance_to_cbd_km", "job_accessibility"):
        assert name in names
    # base terms keep their positions (report reads pvalues[3] as the interaction;
    # fit_ols_robust prepends 'const', so the interaction must sit at index 3)
    assert names[:4] == ['const', 'commute_min_proxy', 'low_income', 'commute*low_income']


def test_rq2_job_accessibility_anova_present(sample_zcta_df) -> None:
    result = analyze_rq2(sample_zcta_df)
    anova_vars = [ar.variable for ar in result.anova_results]
    assert 'job_accessibility' in anova_vars


def test_rq2_still_runs_without_employment_columns(sample_zcta_df) -> None:
    df = sample_zcta_df.drop(["job_density", "distance_to_cbd_km", "job_accessibility"])
    result = analyze_rq2(df)
    assert result.interaction_model is not None
    assert 'job_density' not in result.interaction_model['feature_names']
