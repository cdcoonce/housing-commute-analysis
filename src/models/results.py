"""Typed result containers for analysis outputs.

Each dataclass captures the structured output of an RQ analysis function,
decoupling statistical computation from file I/O and report formatting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import polars as pl


@dataclass(frozen=True)
class RQ1Results:
    """Results from RQ1 housing-commute trade-off analysis.

    Attributes
    ----------
    model_linear : dict[str, Any]
        Linear model fit_ols_robust() output.
    model_quad : dict[str, Any]
        Quadratic model fit_ols_robust() output.
    best_model_name : str
        'Linear' or 'Quadratic' (selected by AIC).
    best_model : dict[str, Any]
        The selected model's fit_ols_robust() output.
    cv_rmse_linear : float
        3-fold CV-RMSE for the linear model.
    cv_rmse_quad : float
        3-fold CV-RMSE for the quadratic model.
    vif_linear : Any
        VIF DataFrame for linear model.
    vif_quad : Any
        VIF DataFrame for quadratic model.
    y_pred : np.ndarray
        Predicted values from the best model.
    residuals : np.ndarray
        Residuals from the best model.
    y_true : np.ndarray
        Observed rent_to_income values.
    commute_time : np.ndarray
        Commute time values (for plotting).
    feature_matrix : np.ndarray
        Best model's feature matrix.
    feature_names : list[str]
        Best model's feature names.
    sample_size : int
        Number of ZCTAs in the analysis.
    model_df : pl.DataFrame
        DataFrame with ZCTA IDs, actual values, predictions, and residuals.
    """

    model_linear: dict[str, Any]
    model_quad: dict[str, Any]
    best_model_name: str
    best_model: dict[str, Any]
    cv_rmse_linear: float
    cv_rmse_quad: float
    vif_linear: Any
    vif_quad: Any
    y_pred: np.ndarray
    residuals: np.ndarray
    y_true: np.ndarray
    commute_time: np.ndarray
    feature_matrix: np.ndarray
    feature_names: list[str]
    sample_size: int
    model_df: pl.DataFrame


@dataclass
class ANOVAResult:
    """Single ANOVA test result.

    Attributes
    ----------
    variable : str
        Name of the variable tested (e.g., 'Rent Burden').
    f_stat : float | None
        F-statistic, or None if test was not performed.
    p_value : float | None
        P-value, or None if test was not performed.
    """

    variable: str
    f_stat: Optional[float] = None
    p_value: Optional[float] = None

    @property
    def significant(self) -> bool:
        """Whether the ANOVA is significant at alpha=0.05."""
        return self.p_value is not None and self.p_value < 0.05


@dataclass
class RQ2Results:
    """Results from RQ2 equity analysis.

    Attributes
    ----------
    interaction_model : dict[str, Any] | None
        Interaction model output from fit_ols_robust(), or None.
    rent_by_income : pl.DataFrame | None
        Group-level rent burden statistics.
    commute_by_income : pl.DataFrame | None
        Group-level long commute statistics.
    anova_results : list[ANOVAResult]
        List of ANOVA test results for each variable tested.
    cluster_summary : pl.DataFrame | None
        K-means cluster center summary.
    cluster_labels : np.ndarray | None
        Cluster assignment per ZCTA.
    df_with_segments : pl.DataFrame | None
        DataFrame with income_segment and majority_race added.
    """

    interaction_model: Optional[dict[str, Any]] = None
    rent_by_income: Optional[pl.DataFrame] = None
    commute_by_income: Optional[pl.DataFrame] = None
    anova_results: list[ANOVAResult] = field(default_factory=list)
    cluster_summary: Optional[pl.DataFrame] = None
    cluster_labels: Optional[np.ndarray] = None
    df_with_segments: Optional[pl.DataFrame] = None


@dataclass
class RQ3Results:
    """Results from RQ3 ACI analysis.

    Attributes
    ----------
    aci_model : dict[str, Any] | None
        OLS model output from fit_ols_robust().
    quantile_results : dict[float, Any]
        Quantile regression results keyed by tau.
    cv_rmse_aci : float | None
        5-fold CV-RMSE for the ACI model.
    tier_summary : pl.DataFrame | None
        ACI tier distribution summary.
    feature_names : list[str]
        Feature names used in the ACI model.
    df_with_aci : pl.DataFrame | None
        DataFrame with ACI, rent_z, commute_z columns added.
    """

    aci_model: Optional[dict[str, Any]] = None
    quantile_results: dict[float, Any] = field(default_factory=dict)
    cv_rmse_aci: Optional[float] = None
    tier_summary: Optional[pl.DataFrame] = None
    feature_names: list[str] = field(default_factory=list)
    df_with_aci: Optional[pl.DataFrame] = None
