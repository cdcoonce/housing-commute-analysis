"""Tests for src.models.models statistical modeling utilities."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.models.models import (
    calculate_vif,
    cv_rmse,
    fit_ols_robust,
    fit_quantile_regression,
)

EXPECTED_OLS_KEYS = {
    "results",
    "adj_r2",
    "aic",
    "bic",
    "params",
    "pvalues",
    "std_errors",
    "feature_names",
}


class TestFitOlsRobust:
    """Tests for fit_ols_robust."""

    def test_fit_ols_robust_returns_dict(self, numpy_X_y: tuple) -> None:
        """fit_ols_robust should return a dict containing all expected keys."""
        X, y = numpy_X_y
        result = fit_ols_robust(y, X, feature_names=["a", "b", "c"])

        assert isinstance(result, dict)
        assert result.keys() == EXPECTED_OLS_KEYS

    def test_fit_ols_robust_adj_r2_range(self, numpy_X_y: tuple) -> None:
        """Adjusted R-squared should fall in [0, 1] for well-behaved data."""
        X, y = numpy_X_y
        result = fit_ols_robust(y, X)

        assert 0.0 <= result["adj_r2"] <= 1.0

    def test_fit_ols_robust_params_length(self, numpy_X_y: tuple) -> None:
        """Parameter vector length should equal n_features + 1 for the constant."""
        X, y = numpy_X_y
        result = fit_ols_robust(y, X)

        n_features = X.shape[1]
        assert len(result["params"]) == n_features + 1

    def test_fit_ols_robust_mismatched_shapes(self, numpy_X_y: tuple) -> None:
        """Should raise ValueError when X and y have different sample counts."""
        X, y = numpy_X_y

        with pytest.raises(ValueError, match="mismatch"):
            fit_ols_robust(y[:10], X)

    def test_fit_ols_robust_feature_names(self, numpy_X_y: tuple) -> None:
        """Returned feature_names should be ['const'] + input names."""
        X, y = numpy_X_y
        names = ["alpha", "beta", "gamma"]
        result = fit_ols_robust(y, X, feature_names=names)

        assert result["feature_names"] == ["const"] + names


class TestCvRmse:
    """Tests for cv_rmse."""

    def test_cv_rmse_returns_median_and_folds(self, numpy_X_y: tuple) -> None:
        """Should return (float, list) where the list has k elements."""
        X, y = numpy_X_y
        k = 5
        median_rmse, fold_rmses = cv_rmse(X, y, k=k)

        assert isinstance(median_rmse, float)
        assert isinstance(fold_rmses, list)
        assert len(fold_rmses) == k

    def test_cv_rmse_k_less_than_2(self, numpy_X_y: tuple) -> None:
        """Should raise ValueError when k < 2."""
        X, y = numpy_X_y

        with pytest.raises(ValueError, match="at least 2"):
            cv_rmse(X, y, k=1)

    def test_cv_rmse_mismatched_shapes(self, numpy_X_y: tuple) -> None:
        """Should raise ValueError when X and y have different sample counts."""
        X, y = numpy_X_y

        with pytest.raises(ValueError, match="mismatch"):
            cv_rmse(X[:10], y)

    def test_cv_rmse_reproducibility(self, numpy_X_y: tuple) -> None:
        """Identical inputs should produce identical RMSE across calls."""
        X, y = numpy_X_y
        median1, folds1 = cv_rmse(X, y, k=3)
        median2, folds2 = cv_rmse(X, y, k=3)

        assert median1 == median2
        assert folds1 == folds2


class TestCalculateVif:
    """Tests for calculate_vif."""

    def test_calculate_vif_returns_dataframe(self, numpy_X_y: tuple) -> None:
        """Should return a pandas DataFrame with 'Feature' and 'VIF' columns."""
        X, _ = numpy_X_y
        result = calculate_vif(X, feature_names=["a", "b", "c"])

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["Feature", "VIF"]

    def test_calculate_vif_uncorrelated(self) -> None:
        """VIF should be approximately 1.0 for independent random columns."""
        np.random.seed(99)
        X = np.random.randn(500, 3)
        result = calculate_vif(X, feature_names=["x0", "x1", "x2"])

        for vif_value in result["VIF"]:
            assert vif_value == pytest.approx(1.0, abs=0.15)

    def test_calculate_vif_highly_correlated(self) -> None:
        """VIF should exceed 10 for nearly collinear features."""
        np.random.seed(99)
        x1 = np.random.randn(200)
        x2 = x1 + np.random.randn(200) * 0.01  # nearly identical to x1
        x3 = np.random.randn(200)
        X = np.column_stack([x1, x2, x3])

        result = calculate_vif(X, feature_names=["x1", "x2", "x3"])
        max_vif = result["VIF"].max()

        assert max_vif > 10


class TestFitQuantileRegression:
    """Tests for fit_quantile_regression."""

    @pytest.mark.parametrize("tau", [0.0, 1.0])
    def test_fit_quantile_regression_invalid_tau(
        self, numpy_X_y: tuple, tau: float
    ) -> None:
        """Should raise ValueError for quantile values at boundaries 0 and 1."""
        X, y = numpy_X_y

        with pytest.raises(ValueError, match="Quantile must be in"):
            fit_quantile_regression(y, X, quantile=tau)
