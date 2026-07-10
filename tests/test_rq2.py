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
