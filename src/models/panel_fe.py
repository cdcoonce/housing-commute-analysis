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

Weighted estimation (design-doc section 4 diagnostics)
------------------------------------------------------
``within_fe`` optionally takes per-observation ``weights`` (RQ4 use case:
cross-sectional, time-invariant renter counts ``renter_share x total_pop``).
The Frisch-Waugh-Lovell projection onto the absorbed unit dummies is then the
*weighted* projection: demeaning subtracts WEIGHTED unit means from the
outcome and every design column (including the explicit time dummies), and
the demeaned regression runs as WLS with the same weights. This is exactly
equivalent to weighted LSDV (WLS on explicit unit + time dummies) — the
whitened demeaned columns are the whitened-LSDV residuals of the unit-dummy
block — so coefficients, the cluster-robust covariance, and the dof rescale
all carry over unchanged. Weights must be finite and strictly positive;
degenerate weights raise ``ValueError`` naming the offending units.
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


def _validate_weights(weights: np.ndarray, unit_ids: np.ndarray) -> np.ndarray:
    """Return ``weights`` as a float array, rejecting degenerate values.

    Zero, negative, and non-finite (NaN/inf) weights raise ``ValueError``
    naming the offending unit labels so the caller can trace them to source
    rows (ZCTAs, in the RQ4 use case).
    """
    w = np.asarray(weights, dtype=float)
    bad = ~np.isfinite(w) | (w <= 0.0)
    if bad.any():
        offenders = sorted({str(u) for u in np.asarray(unit_ids)[bad]})
        raise ValueError(
            "weights must be finite and strictly positive; offending "
            f"unit(s): {', '.join(offenders)}"
        )
    return w


def _demean_within(
    values: np.ndarray,
    groups: pd.Series,
    weights: np.ndarray | None = None,
) -> np.ndarray:
    """Subtract (optionally weighted) group means from each column of ``values``."""
    frame = pd.DataFrame(values)
    if weights is None:
        means = frame.groupby(groups).transform("mean")
    else:
        w = pd.Series(weights, index=frame.index)
        means = (
            frame.mul(w, axis=0).groupby(groups).transform("sum")
        ).div(w.groupby(groups).transform("sum"), axis=0)
    return (frame - means).to_numpy()


def _within_design(
    y: np.ndarray,
    X: np.ndarray,
    unit_ids: np.ndarray,
    time_ids: np.ndarray,
    weights: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, int, pd.Series]:
    """Within-transform shared by the estimator and the bootstrap.

    Returns the unit-demeaned outcome, the unit-demeaned design
    ``[X | time dummies]`` (first period dropped), the count of supplied
    regressors, and the unit labels as a Series. With ``weights``, the
    demeaning projections use WEIGHTED unit means (the WLS Frisch-Waugh-
    Lovell projection onto the absorbed unit dummies — see module docstring).
    """
    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X[:, None]

    units = pd.Series(np.asarray(unit_ids))
    time_dummies = pd.get_dummies(
        pd.Series(np.asarray(time_ids)), drop_first=True
    ).to_numpy(dtype=float)
    design = np.column_stack([X, time_dummies])

    y_within = _demean_within(y[:, None], units, weights).ravel()
    design_within = _demean_within(design, units, weights)
    return y_within, design_within, X.shape[1], units


def within_fe(
    y: np.ndarray,
    X: np.ndarray,
    unit_ids: np.ndarray,
    time_ids: np.ndarray,
    cluster_ids: np.ndarray,
    weights: np.ndarray | None = None,
) -> FEResult:
    """Two-way FE regression of ``y`` on ``X`` via the within transform.

    Time effects enter as explicit dummies (first period dropped) and both
    the outcome and the full design are demeaned within unit, so coefficients
    equal two-way LSDV exactly on balanced *and* unbalanced panels. With
    ``weights``, demeaning uses weighted unit means and the demeaned
    regression runs as WLS — exactly weighted LSDV (module docstring); with
    all-equal weights this reproduces the unweighted estimator exactly.

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
    weights : np.ndarray, optional
        Per-observation weights, shape (N,); must be finite and strictly
        positive (``ValueError`` names offending units otherwise). The RQ4
        renter-weighted robustness passes per-ZCTA time-invariant renter
        counts.

    Returns
    -------
    FEResult
        Coefficients, SEs, and covariance for the ``X`` block only.

    Raises
    ------
    ValueError
        If the unit-demeaned design ``[X | time dummies]`` is rank-deficient
        (collinear ``X``, or a time period identified only through absorbed
        units) -- otherwise the pinv-based fit would silently break LSDV
        equality and the dof rescale would use the wrong K. Also if the
        rescale denominator ``N - K - G_absorbed`` is not positive, which
        would otherwise surface as NaN / negative-variance ``bse``; the
        message reports the actual N, K, and G_absorbed. Degenerate
        ``weights`` raise as documented above.
    """
    if weights is not None:
        weights = _validate_weights(weights, unit_ids)
    y_within, design_within, k_x, units = _within_design(
        y, X, unit_ids, time_ids, weights
    )

    n_obs = int(y_within.size)
    n_units = int(units.nunique())
    k_within = design_within.shape[1]
    # Rank guard: statsmodels falls back to pinv on singular designs, which
    # would silently degrade LSDV equality (and make K wrong in the rescale).
    # Strictly positive weights make WLS whitening a full-rank row scaling,
    # so the rank of the demeaned design covers the weighted path too.
    rank = int(np.linalg.matrix_rank(design_within))
    if rank < k_within:
        raise ValueError(
            f"within design is rank-deficient: rank {rank} < {k_within} "
            f"columns ({k_x} supplied regressor(s) + "
            f"{k_within - k_x} time dummies, unit-demeaned); check for "
            "collinear X or a time period observed only in singleton units"
        )
    dof = n_obs - k_within - n_units
    if dof <= 0:
        raise ValueError(
            "degrees of freedom exhausted in the dof rescale: "
            f"N - K - G_absorbed = {n_obs} - {k_within} - {n_units} = "
            f"{dof} <= 0; the LSDV-matching correction is undefined on "
            "this panel"
        )

    if weights is None:
        model = sm.OLS(y_within, design_within)
    else:
        model = sm.WLS(y_within, design_within, weights=weights)
    fit = model.fit(
        cov_type="cluster", cov_kwds={"groups": np.asarray(cluster_ids)}
    )

    rescale = (n_obs - k_within) / dof
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


#: Webb's six-point wild-bootstrap weight distribution — recommended over
#: Rademacher when the cluster count is small (< ~12 distinct t* values
#: otherwise), which is exactly the thin-identification / ZIP3 use case.
WEBB_WEIGHTS = np.array(
    [-np.sqrt(1.5), -1.0, -np.sqrt(0.5), np.sqrt(0.5), 1.0, np.sqrt(1.5)]
)


def wild_cluster_boot_p(
    y: np.ndarray,
    X: np.ndarray,
    unit_ids: np.ndarray,
    time_ids: np.ndarray,
    cluster_ids: np.ndarray,
    coef_idx: int,
    n_boot: int = 999,
    seed: int = 0,
) -> float:
    """Restricted (null-imposed) wild cluster bootstrap p-value, Webb weights.

    Tests ``H0: beta[coef_idx] = 0`` in the two-way FE model estimated by
    :func:`within_fe`. The restricted model (H0 imposed) is fit on the
    within-transformed data; each bootstrap outcome resamples the restricted
    residuals with a single Webb six-point weight per cluster, and the
    absolute studentized statistic is compared against the original. This is
    the Cameron-Gelbach-Miller WCR bootstrap, the appropriate inference for
    few / few-effective clusters (design section 4, estimator layer 3:
    thin-identification metros and ZIP3 coarse-cluster spatial robustness).

    ``cluster_ids`` must nest ``unit_ids`` (each unit inside exactly one
    cluster — true for ZCTA-level and ZIP3-prefix clustering). Nesting makes
    the per-cluster weight constant within each unit, so weighting commutes
    with the within transform and the bootstrap can run entirely in the
    demeaned space.

    Parameters
    ----------
    y, X, unit_ids, time_ids, cluster_ids
        As in :func:`within_fe`.
    coef_idx : int
        Position (into the ``X`` block) of the coefficient under the null.
    n_boot : int
        Bootstrap replications (999 keeps ``alpha * (n_boot + 1)`` integral
        at conventional levels).
    seed : int
        Seed for the weight draws; fixed seed gives a deterministic p-value.

    Returns
    -------
    float
        Symmetric bootstrap p-value: the share of bootstrap ``|t*|`` at or
        above the observed ``|t|``.
    """
    clusters = pd.Series(np.asarray(cluster_ids))
    cluster_codes, uniques = pd.factorize(clusters)
    n_clusters = len(uniques)
    if n_clusters < 3:
        raise ValueError(
            f"wild cluster bootstrap needs >= 3 clusters, got {n_clusters}"
        )
    if clusters.groupby(np.asarray(unit_ids)).nunique().gt(1).any():
        raise ValueError("cluster_ids must nest unit_ids (one cluster per unit)")

    y_w, design_w, _, _ = _within_design(y, X, unit_ids, time_ids)
    n_obs, k = design_w.shape

    xtx_inv = np.linalg.inv(design_w.T @ design_w)
    a = xtx_inv[:, coef_idx]                     # row of (X'X)^-1 for the test
    z = design_w @ a                             # contracts cluster scores to var_jj
    cr1 = (n_clusters / (n_clusters - 1)) * ((n_obs - 1) / (n_obs - k))
    members = np.zeros((n_clusters, n_obs))      # cluster-sum operator
    members[cluster_codes, np.arange(n_obs)] = 1.0

    def studentized(outcomes: np.ndarray) -> np.ndarray:
        """Cluster-robust t for beta[coef_idx], per column of ``outcomes``."""
        beta_j = a @ (design_w.T @ outcomes)
        resid = outcomes - design_w @ (xtx_inv @ (design_w.T @ outcomes))
        per_cluster = members @ (z[:, None] * resid)
        return beta_j / np.sqrt(cr1 * (per_cluster**2).sum(axis=0))

    t_obs = studentized(y_w[:, None])[0]

    restricted = np.delete(design_w, coef_idx, axis=1)
    beta_r, *_ = np.linalg.lstsq(restricted, y_w, rcond=None)
    fitted_r = restricted @ beta_r
    resid_r = y_w - fitted_r

    rng = np.random.default_rng(seed)
    draws = rng.choice(WEBB_WEIGHTS, size=(n_clusters, n_boot))
    boot_outcomes = fitted_r[:, None] + resid_r[:, None] * draws[cluster_codes, :]
    t_boot = studentized(boot_outcomes)

    return float(np.mean(np.abs(t_boot) >= np.abs(t_obs)))
