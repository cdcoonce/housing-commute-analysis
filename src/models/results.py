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
    threshold : dict[str, Any]
        Drive-until-you-qualify threshold estimate from the quadratic model:
        keys t_star, se, ci_low, ci_high (floats or None), valid (bool), and
        reason (str or None). The vertex t* = -B1/(2*B2) with a delta-method
        SE is reported only when curvature is significantly concave and t*
        lies within the observed commute range; otherwise valid is False and
        reason explains why no threshold is claimed.
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
    threshold: dict[str, Any]


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


@dataclass(frozen=True)
class RQ4Results:
    """Results from RQ4 ZORI rent-dynamics analysis (design doc section 5).

    All estimation is per metro. Model dicts are the within-FE estimator
    outputs (coefficients, cluster-robust SEs, p-values, metadata such as
    ``x_vintage``); frames are diagnostic tables destined for the report.

    Attributes
    ----------
    gradient_model_joint : dict[str, Any]
        Spec A headline: two-phase (Post1/Post2) joint interaction model over
        the three pre-COVID gradient regressors.
    gradient_models_single : dict[str, dict[str, Any]]
        One single-interaction model per gradient variable (sign robustness),
        keyed by regressor name (e.g. ``distance_to_cbd_km``).
    gradient_model_pooled : dict[str, Any]
        Single-Post pooled summary, explicitly averaging the two phases.
    wald_break : dict[str, Any]
        Cluster-robust Wald tests keyed ``phase1``/``phase2``/``pooled``.
    bootstrap_pvalues : dict[str, Any]
        Webb wild-cluster bootstrap p-values (thin-identification metros and
        ZIP3 coarse-cluster robustness), keyed by regressor name.
    event_study : pl.DataFrame
        Spec B: variable x event-time bin with coef/se/ci and per-bin
        identifying ZCTA counts.
    access_model : dict[str, Any]
        Spec C: time-varying annual accessibility model (truncated 2023-12).
    mediation : dict[str, Any]
        Spec C-med: mediation decomposition (share of Post1 repricing running
        through contemporaneous access), never labeled robustness.
    chase_model_lagged : dict[str, Any]
        Spec D: annual mean log rent on lagged log access (predictive
        association, no causal claim).
    chase_model_lead : dict[str, Any]
        Spec D falsification: lead access term (significant lead = feedback).
    chase_model_contemp : dict[str, Any]
        Spec D robustness: contemporaneous access variant.
    long_difference : dict[str, Any]
        Long-difference association, keyed by window (2015-2019, 2019-2023).
    vintage2021_robustness : dict[str, Any]
        Measured-gradient sensitivity: 2021-vintage proxy + LODES-2021 access.
    n_obs : int
        Estimation-sample (i, t) cell count after trims/drops.
    n_zctas : int
        Distinct ZCTAs in the estimation sample.
    n_identifying : int
        ZCTAs observed both pre and post break (identify the interactions).
    n_pre_months : int
        Distinct pre-break months in the estimation sample.
    n_post_months : int
        Distinct post-break months after endpoint trim and transition drop.
    coverage : dict[str, Any]
        Panel coverage diagnostics (covered-ZCTA shares over time).
    balanced_robustness : dict[str, Any]
        Balanced-subpanel bound (ZCTAs in-sample by 2019-01).
    entrant_composition : pl.DataFrame
        Mean of each gradient x for post-2019-12 entrants vs incumbents.
    flags : list[str]
        Quality flags, e.g. ``under_identified`` when n_identifying < 20.
    """

    gradient_model_joint: dict[str, Any]
    gradient_models_single: dict[str, dict[str, Any]]
    gradient_model_pooled: dict[str, Any]
    wald_break: dict[str, Any]
    bootstrap_pvalues: dict[str, Any]
    event_study: pl.DataFrame
    access_model: dict[str, Any]
    mediation: dict[str, Any]
    chase_model_lagged: dict[str, Any]
    chase_model_lead: dict[str, Any]
    chase_model_contemp: dict[str, Any]
    long_difference: dict[str, Any]
    vintage2021_robustness: dict[str, Any]
    n_obs: int
    n_zctas: int
    n_identifying: int
    n_pre_months: int
    n_post_months: int
    coverage: dict[str, Any]
    balanced_robustness: dict[str, Any]
    entrant_composition: pl.DataFrame
    flags: list[str]
