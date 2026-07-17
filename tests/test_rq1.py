"""Tests for RQ1 housing-commute trade-off analysis (pure analyze half)."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from src.models.results import RQ1Results
from src.models.rq1_housing_commute_tradeoff import analyze_rq1, report_rq1


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


def _synth_quadratic_df(
    b1: float,
    b2: float,
    *,
    n: int = 240,
    noise_sd: float = 1e-3,
    seed: int = 7,
) -> pl.DataFrame:
    """Synthetic ZCTA frame where rent_to_income is a known quadratic in commute.

    y = 0.05 + b1*commute + b2*commute^2 + N(0, noise_sd); the other predictors
    are random noise with true coefficient zero, so the quadratic fit recovers
    (b1, b2) and the vertex t* = -b1/(2*b2) almost exactly.
    """
    rng = np.random.default_rng(seed)
    commute = rng.uniform(15.0, 45.0, n)
    y = 0.05 + b1 * commute + b2 * commute**2 + rng.normal(0.0, noise_sd, n)
    return pl.DataFrame({
        "ZCTA5CE": [f"{85000 + i}" for i in range(n)],
        "rent_to_income": y,
        "commute_min_proxy": commute,
        "renter_share": rng.uniform(0.2, 0.8, n),
        "vehicle_access": rng.uniform(0.5, 0.98, n),
        "pop_density": rng.uniform(100.0, 5000.0, n),
        "job_density": rng.uniform(10.0, 2000.0, n),
        "distance_to_cbd_km": rng.uniform(1.0, 40.0, n),
        "job_accessibility": rng.uniform(1_000.0, 200_000.0, n),
    })


def test_threshold_recovers_known_vertex() -> None:
    # Concave quadratic with vertex at t* = -b1/(2*b2) = 30 min, inside [15, 45].
    b1, b2 = 0.024, -0.0004
    true_t_star = -b1 / (2 * b2)
    result = analyze_rq1(_synth_quadratic_df(b1, b2))
    thr = result.threshold
    assert thr["valid"] is True
    assert thr["reason"] is None
    assert abs(thr["t_star"] - true_t_star) < 0.5
    assert thr["se"] > 0
    assert math.isfinite(thr["se"])
    assert thr["ci_low"] < thr["t_star"] < thr["ci_high"]
    assert abs((thr["ci_high"] - thr["t_star"]) - 1.96 * thr["se"]) < 1e-9


def test_threshold_convex_curvature_not_claimed() -> None:
    # Convex (b2 > 0): the vertex is a minimum, not a tradeoff threshold.
    result = analyze_rq1(_synth_quadratic_df(-0.024, 0.0004))
    thr = result.threshold
    assert thr["valid"] is False
    assert thr["reason"] == "convex or insignificant curvature"
    assert thr["t_star"] is None


def test_threshold_vertex_outside_observed_range() -> None:
    # Concave but vertex at 60 min, outside the observed [15, 45] range.
    result = analyze_rq1(_synth_quadratic_df(0.048, -0.0004))
    thr = result.threshold
    assert thr["valid"] is False
    assert thr["reason"] == "vertex outside observed range"


def test_report_rq1_threshold_section_and_model_spec_prose(tmp_path: Path) -> None:
    out = tmp_path / "out"
    fig = tmp_path / "fig"
    out.mkdir()
    fig.mkdir()
    report_rq1(analyze_rq1(_synth_quadratic_df(0.024, -0.0004)), out, fig, "PHX")
    text = (out / "analysis_summary_phx.md").read_text()
    assert "Drive-Until-You-Qualify Threshold" in text
    assert "95% CI" in text
    # Model-spec prose must name all eight predictors, not just B1-B5.
    for term in (
        "B6(job_density)",
        "B7(distance_to_cbd_km)",
        "B8(job_accessibility)",
    ):
        assert term in text
