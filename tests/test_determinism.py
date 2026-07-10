"""Determinism: seeded analysis is byte-stable across repeated runs."""
from __future__ import annotations

import numpy as np
import polars as pl

from src.models.models import cv_rmse
from src.models.rq2_equity_analysis import analyze_rq2


def test_cv_rmse_repeatable() -> None:
    rng = np.random.default_rng(0)
    X = rng.standard_normal((40, 3))
    y = X @ np.array([1.0, -0.5, 0.2]) + rng.standard_normal(40) * 0.1
    m1, folds1 = cv_rmse(X, y, k=3)
    m2, folds2 = cv_rmse(X, y, k=3)
    assert m1 == m2
    assert folds1 == folds2


def test_rq2_clusters_repeatable(sample_zcta_df: pl.DataFrame) -> None:
    r1 = analyze_rq2(sample_zcta_df)
    r2 = analyze_rq2(sample_zcta_df)
    if r1.cluster_labels is not None and r2.cluster_labels is not None:
        assert np.array_equal(r1.cluster_labels, r2.cluster_labels)
