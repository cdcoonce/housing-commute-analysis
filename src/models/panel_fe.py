"""Two-way fixed-effects within estimator with honest cluster-robust inference.

Implements the design-doc §4 "Estimator and inference" layer for RQ4: a
Frisch-Waugh-Lovell within transform (demean the outcome and every regressor
-- including explicit time dummies -- within unit), then OLS with
cluster-robust standard errors and an explicit degrees-of-freedom rescale so
the reported covariance is exactly what two-way LSDV would produce.

Degrees-of-freedom convention (a deliberate choice, not an error)
-----------------------------------------------------------------
With unit fixed effects nested inside the clusters, the Cameron-Miller /
reghdfe convention *omits* the absorbed fixed effects from K in the
small-sample correction. This implementation goes the opposite, deliberately
conservative direction: the within-OLS clustered covariance is rescaled by

    (N - K) / (N - K - G_absorbed)

where K counts the regressors actually present in the within regression and
G_absorbed counts the absorbed unit-FE parameters (intercept plus unit
dummies). That reproduces the LSDV correction (N - 1) / (N - K_LSDV) exactly,
inflating SEs by well under 1% at this project's N. See ``DOF_NOTE``.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

DOF_NOTE = (
    "Deliberately conservative dof convention: the clustered covariance from "
    "the within regression is rescaled by (N-K)/(N-K-G_absorbed), matching "
    "two-way LSDV which counts absorbed fixed effects in K. The "
    "Cameron-Miller/reghdfe convention omits nested absorbed FE from K; we "
    "inflate instead."
)


@dataclass(frozen=True)
class FEResult:
    """Within-estimator output for the non-absorbed regressors only.

    Attributes
    ----------
    params : np.ndarray
        Coefficients on the K_x supplied regressors (absorbed unit/time
        effects and time dummies are not reported).
    bse : np.ndarray
        Cluster-robust standard errors under the documented dof convention.
    cov : np.ndarray
        (K_x, K_x) cluster-robust covariance under the same convention.
    n_obs : int
        Number of observations entering the regression.
    n_units : int
        Number of distinct units (absorbed fixed-effect groups).
    dof_note : str
        The documented dof convention (see module docstring).
    """

    params: np.ndarray
    bse: np.ndarray
    cov: np.ndarray
    n_obs: int
    n_units: int
    dof_note: str


def _demean_within(values: np.ndarray, groups: pd.Series) -> np.ndarray:
    """Subtract group means from each column of ``values``."""
    frame = pd.DataFrame(values)
    return (frame - frame.groupby(groups).transform("mean")).to_numpy()


def within_fe(
    y: np.ndarray,
    X: np.ndarray,
    unit_ids: np.ndarray,
    time_ids: np.ndarray,
    cluster_ids: np.ndarray,
) -> FEResult:
    """Two-way FE regression of ``y`` on ``X`` via the within transform.

    Time effects enter as explicit dummies (first period dropped) and both
    the outcome and the full design are demeaned within unit, so coefficients
    equal two-way LSDV exactly on balanced *and* unbalanced panels.

    Parameters
    ----------
    y : np.ndarray
        Outcome, shape (N,).
    X : np.ndarray
        Regressors of interest, shape (N, K_x) or (N,).
    unit_ids : np.ndarray
        Unit (absorbed FE) label per observation.
    time_ids : np.ndarray
        Time-period label per observation.
    cluster_ids : np.ndarray
        Cluster label per observation for the robust covariance.

    Returns
    -------
    FEResult
        Coefficients, SEs, and covariance for the ``X`` block only.
    """
    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    k_x = X.shape[1]

    units = pd.Series(np.asarray(unit_ids))
    time_dummies = pd.get_dummies(
        pd.Series(np.asarray(time_ids)), drop_first=True
    ).to_numpy(dtype=float)
    design = np.column_stack([X, time_dummies])

    y_within = _demean_within(y[:, None], units).ravel()
    design_within = _demean_within(design, units)

    fit = sm.OLS(y_within, design_within).fit(
        cov_type="cluster", cov_kwds={"groups": np.asarray(cluster_ids)}
    )

    n_obs = int(y.size)
    n_units = int(units.nunique())
    k_within = design_within.shape[1]
    rescale = (n_obs - k_within) / (n_obs - k_within - n_units)
    cov = np.asarray(fit.cov_params())[:k_x, :k_x] * rescale

    return FEResult(
        params=np.asarray(fit.params)[:k_x],
        bse=np.sqrt(np.diag(cov)),
        cov=cov,
        n_obs=n_obs,
        n_units=n_units,
        dof_note=DOF_NOTE,
    )


def wald_joint(result: FEResult, idx: Sequence[int]) -> tuple[float, float]:
    """Cluster-robust Wald test that the coefficients at ``idx`` are jointly zero.

    Parameters
    ----------
    result : FEResult
        Output of :func:`within_fe`.
    idx : Sequence[int]
        Positions (into ``result.params``) of the coefficients under test.

    Returns
    -------
    tuple[float, float]
        (Wald statistic, chi-squared p-value with ``len(idx)`` dof).
    """
    idx = list(idx)
    b = result.params[idx]
    v = result.cov[np.ix_(idx, idx)]
    stat = float(b @ np.linalg.solve(v, b))
    p = float(stats.chi2.sf(stat, df=len(idx)))
    return stat, p
