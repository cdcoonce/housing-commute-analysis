"""Tests for RQ3 ACI analysis (pure analyze half)."""
from __future__ import annotations

import warnings

import numpy as np
import polars as pl
import pytest
from statsmodels.tools.sm_exceptions import IterationLimitWarning

import src.models.rq3_aci_analysis as rq3
from src.models.results import RQ3Results
from src.models.rq3_aci_analysis import analyze_rq3


def test_analyze_rq3_aci_is_sum_of_zscores(sample_zcta_df: pl.DataFrame) -> None:
    result = analyze_rq3(sample_zcta_df)
    assert isinstance(result, RQ3Results)
    df = result.df_with_aci
    assert df is not None
    rent = df["rent_to_income"]
    commute = df["commute_min_proxy"]
    rent_z = (rent - rent.mean()) / rent.std()        # polars std is sample (ddof=1)
    commute_z = (commute - commute.mean()) / commute.std()
    expected = (rent_z + commute_z).to_numpy()
    assert np.allclose(df["ACI"].to_numpy(), expected, rtol=1e-9, atol=1e-9)


def test_analyze_rq3_quantile_keys(sample_zcta_df: pl.DataFrame) -> None:
    result = analyze_rq3(sample_zcta_df)
    assert set(result.quantile_results.keys()).issubset({0.25, 0.5, 0.75})


def test_rq3_includes_employment_candidates(sample_zcta_df: pl.DataFrame) -> None:
    result = analyze_rq3(sample_zcta_df)
    for name in ("job_density", "distance_to_cbd_km", "job_accessibility"):
        assert name in result.feature_names


def test_rq3_still_runs_without_employment_columns(sample_zcta_df: pl.DataFrame) -> None:
    df = sample_zcta_df.drop(["job_density", "distance_to_cbd_km", "job_accessibility"])
    result = analyze_rq3(df)
    assert result.aci_model is not None
    assert 'job_density' not in result.feature_names


def test_quantile_results_converged_true_on_well_conditioned_fixture(
    sample_zcta_df: pl.DataFrame,
) -> None:
    result = analyze_rq3(sample_zcta_df)
    for tau, entry in result.quantile_results.items():
        assert entry["converged"] is True, f"tau={tau} unexpectedly failed to converge"


def test_quantile_results_converged_false_when_iteration_cap_hit(
    monkeypatch: pytest.MonkeyPatch, sample_zcta_df: pl.DataFrame
) -> None:
    """A solver that hits its iteration cap is reported as not converged.

    The cap is provoked by making ``QuantReg.fit`` emit the warning
    statsmodels raises in that situation, rather than by feeding the solver an
    ill-conditioned fixture and hoping it fails to converge. Whether a given
    fixture actually exhausts ``max_iter`` depends on the installed BLAS/LAPACK
    build, so the fixture-based form passed locally and failed intermittently
    on CI across Python versions. This form pins the behaviour under test --
    that an ``IterationLimitWarning`` is detected and recorded -- and is
    independent of the linear-algebra backend.
    """
    real_fit = rq3.QuantReg.fit

    def fit_at_iteration_cap(self, *args, **kwargs):
        warnings.warn(
            "Maximum number of iterations (2000) reached.",
            IterationLimitWarning,
            stacklevel=2,
        )
        return real_fit(self, *args, **kwargs)

    monkeypatch.setattr(rq3.QuantReg, "fit", fit_at_iteration_cap)

    result = analyze_rq3(sample_zcta_df)

    assert result.quantile_results, "expected quantile fits to have run"
    assert all(
        entry["converged"] is False for entry in result.quantile_results.values()
    ), result.quantile_results
