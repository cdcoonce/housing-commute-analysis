"""LSDV-equality and inference tests for the within-FE estimator."""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from src.models.panel_fe import wald_joint, within_fe


def _synthetic_panel(seed: int = 7, n_units: int = 30, n_periods: int = 24):
    rng = np.random.default_rng(seed)
    unit = np.repeat(np.arange(n_units), n_periods)
    time = np.tile(np.arange(n_periods), n_units)
    x = rng.normal(size=unit.size) + 0.5 * (unit % 5)          # unit-correlated regressor
    a_i, g_t = rng.normal(size=n_units), rng.normal(size=n_periods)
    y = 2.0 * x + a_i[unit] + g_t[time] + rng.normal(scale=0.5, size=unit.size)
    return y, x[:, None], unit, time


def test_within_equals_lsdv_coefficients_and_clustered_ses() -> None:
    y, X, unit, time = _synthetic_panel()
    fe = within_fe(y, X, unit, time, cluster_ids=unit)

    dummies = np.column_stack([
        pd.get_dummies(unit, drop_first=True).to_numpy(dtype=float),
        pd.get_dummies(time, drop_first=True).to_numpy(dtype=float),
    ])
    lsdv = sm.OLS(y, np.column_stack([X, dummies, np.ones_like(y)])).fit(
        cov_type="cluster", cov_kwds={"groups": unit}
    )
    assert np.allclose(fe.params[0], lsdv.params[0], rtol=1e-8)
    # SE equality under the STATED convention: LSDV counts absorbed dummies in K,
    # which is exactly what the within path's explicit rescale reproduces.
    assert np.allclose(fe.bse[0], lsdv.bse[0], rtol=1e-6)


def test_known_effect_recovery_ci_covers() -> None:
    hits = 0
    for seed in range(20):
        y, X, unit, time = _synthetic_panel(seed=seed)
        fe = within_fe(y, X, unit, time, cluster_ids=unit)
        lo, hi = fe.params[0] - 1.96 * fe.bse[0], fe.params[0] + 1.96 * fe.bse[0]
        hits += lo <= 2.0 <= hi
    assert hits >= 17          # ~95% coverage, generous band for 20 draws


def test_small_cluster_count_no_nan() -> None:
    y, X, unit, time = _synthetic_panel(n_units=6)
    fe = within_fe(y, X, unit, time, cluster_ids=unit)
    assert np.isfinite(fe.bse).all()


def test_result_metadata_and_dof_note() -> None:
    y, X, unit, time = _synthetic_panel()
    fe = within_fe(y, X, unit, time, cluster_ids=unit)
    assert fe.n_obs == y.size
    assert fe.n_units == 30
    assert fe.cov.shape == (1, 1)
    assert "conservative" in fe.dof_note.lower()


def test_wald_joint_matches_squared_t_and_rejects_strong_effect() -> None:
    y, X, unit, time = _synthetic_panel()
    fe = within_fe(y, X, unit, time, cluster_ids=unit)
    stat, p = wald_joint(fe, [0])
    # Single-coefficient Wald == squared cluster-robust t-stat, chi2(1) p-value.
    assert np.isclose(stat, (fe.params[0] / fe.bse[0]) ** 2, rtol=1e-10)
    assert 0.0 <= p < 0.05     # true effect of 2.0 must reject
