"""Tests for RQ4 (ZORI rent dynamics): results contract, fixtures, analysis.

Task 16 scope: the frozen RQ4Results container and the synthetic
sample_panel_fixtures quadruple that feeds the analysis tests (Tasks 17-19).
Task 17 scope: analyze_rq4 Spec-A family (two-phase structural break on the
pre-COVID gradient, vintage discipline, trims, thin-identification flagging).
Task 18 scope: Spec B event study (event-time bins relative to 2020-03),
Spec C time-varying access (truncated at the last LODES year, no
carry-forward), Spec C-med mediation decomposition, and Spec D annual
predictive-association models (>= 6 months per (i, y) cell, lead
falsification, long differences).
Task 19 scope: run_analysis wiring — HAS_RQ4 optional import mirroring
HAS_RQ2/HAS_RQ3, and the skip-when-panels-absent contract (log line, exit 0,
RQ1-RQ3 unaffected). report_rq4 I/O tests live in test_reporting_output.py.
"""
from __future__ import annotations

import dataclasses
import logging
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from src.models.results import RQ4Results
from src.models.rq4_rent_dynamics import (
    GRADIENT_X_2019,
    MIN_MONTHS_PER_YEAR,
    _repricing_consumed,
    analyze_rq4,
    closing_projection,
    collapse_annual,
    cumulative_repricing,
    event_time_bin,
    is_significant_repricing,
    phase_month_counts,
)
from src.pipelines.schema import (
    validate_acs_commute_2019,
    validate_lodes_panel,
    validate_zori_panel,
)

BREAK_MONTH = date(2020, 3, 31)
POST2_START = date(2022, 1, 31)


@pytest.fixture
def sample_panel_fixtures_thin(
    sample_panel_fixtures: tuple[
        pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame
    ],
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Thin-identification variant of the panel quadruple: 8 identifying ZCTAs.

    All but the first 8 ZCTAs lose their pre-break rows (they become 2020-03
    entrants), so only 8 ZCTAs are observed on both sides of the break --
    below the UNDER_IDENTIFIED_MIN=20 threshold that must trigger the
    under_identified flag and ZCTA-level bootstrap p-values.
    """
    cross, zori_panel, lodes_panel, acs2019 = sample_panel_fixtures
    identified = sorted(set(zori_panel["ZCTA5CE"].to_list()))[:8]
    zori_thin = zori_panel.filter(
        (pl.col("period") >= "2020-03-01")  # ISO strings compare by date
        | pl.col("ZCTA5CE").is_in(identified)
    )
    return cross, zori_thin, lodes_panel, acs2019


def _minimal_rq4_results() -> RQ4Results:
    """Construct an RQ4Results with structurally empty fields."""
    empty = pl.DataFrame()
    return RQ4Results(
        gradient_model_joint={},
        gradient_models_single={},
        gradient_model_pooled={},
        wald_break={},
        bootstrap_pvalues={},
        event_study=empty,
        access_model={},
        mediation={},
        chase_model_lagged={},
        chase_model_lead={},
        chase_model_contemp={},
        long_difference={},
        vintage2021_robustness={},
        n_obs=0,
        n_zctas=0,
        n_identifying=0,
        n_pre_months=0,
        n_post_months=0,
        coverage={},
        balanced_robustness={},
        entrant_composition=empty,
        flags=[],
        repricing_consumed={},
    )


class TestRQ4ResultsContract:
    """RQ4Results is a frozen dataclass with the design-section-5 field list."""

    def test_frozen_assignment_raises(self) -> None:
        results = _minimal_rq4_results()

        with pytest.raises(dataclasses.FrozenInstanceError):
            results.n_obs = 99  # type: ignore[misc]

    def test_field_list_matches_design(self) -> None:
        expected = {
            "gradient_model_joint",
            "gradient_models_single",
            "gradient_model_pooled",
            "wald_break",
            "bootstrap_pvalues",
            "event_study",
            "access_model",
            "mediation",
            "chase_model_lagged",
            "chase_model_lead",
            "chase_model_contemp",
            "long_difference",
            "vintage2021_robustness",
            "n_obs",
            "n_zctas",
            "n_identifying",
            "n_pre_months",
            "n_post_months",
            "coverage",
            "balanced_robustness",
            "entrant_composition",
            "flags",
            "repricing_consumed",
        }
        assert {f.name for f in dataclasses.fields(RQ4Results)} == expected


class TestSamplePanelFixtures:
    """The synthetic quadruple must be valid panel data with planted structure."""

    def test_panels_pass_schema_validators(self, sample_panel_fixtures) -> None:
        _cross, zori_panel, lodes_panel, acs2019 = sample_panel_fixtures

        assert validate_zori_panel(zori_panel) == []
        assert validate_lodes_panel(lodes_panel) == []
        assert validate_acs_commute_2019(acs2019) == []

    def test_panel_spans_break_with_both_post_phases(
        self, sample_panel_fixtures
    ) -> None:
        _cross, zori_panel, _lodes, _acs = sample_panel_fixtures
        periods = zori_panel["period"].str.to_date("%Y-%m-%d")

        assert periods.min() < BREAK_MONTH  # pre-break months present
        assert periods.max() >= POST2_START  # Post2 phase present
        assert zori_panel["period"].n_unique() == 60  # ~30 ZCTAs x 60 months

    def test_has_post_2019_entrants(self, sample_panel_fixtures) -> None:
        """A few ZCTAs first appear after 2019-12 (endogenous-entry diagnostics)."""
        _cross, zori_panel, _lodes, _acs = sample_panel_fixtures
        first_seen = (
            zori_panel.with_columns(
                pl.col("period").str.to_date("%Y-%m-%d").alias("_d")
            )
            .group_by("ZCTA5CE")
            .agg(pl.col("_d").min().alias("entry"))
        )
        n_entrants = first_seen.filter(pl.col("entry") > date(2019, 12, 31)).height

        assert 0 < n_entrants < first_seen.height  # some entrants, mostly incumbents

    def test_vintages_differ_and_frames_align(self, sample_panel_fixtures) -> None:
        """2019 and 2021 commute proxies are planted DIFFERENT (Task-17 vintage
        test relies on it), and all four frames share the ZCTA universe."""
        cross, zori_panel, lodes_panel, acs2019 = sample_panel_fixtures

        merged = acs2019.join(
            cross.select("ZCTA5CE", "commute_min_proxy"), on="ZCTA5CE"
        )
        diffs = (
            merged["commute_min_proxy_2019"] - merged["commute_min_proxy"]
        ).abs()
        assert (diffs > 1e-6).all()

        universe = set(cross["ZCTA5CE"].to_list())
        assert set(zori_panel["ZCTA5CE"].to_list()) <= universe
        assert set(lodes_panel["ZCTA5CE"].to_list()) == universe
        assert set(acs2019["ZCTA5CE"].to_list()) == universe
        assert len(universe) == 30


def test_rq4_recovers_planted_donut_effect(sample_panel_fixtures) -> None:
    cross, zp, lp, acs = sample_panel_fixtures
    r = analyze_rq4(cross, zp, lp, acs)
    d = r.gradient_models_single["distance_to_cbd_km"]
    assert d["post1_coef"] > 0                       # planted repricing found...
    assert d["post1_pvalue"] < 0.05                   # ...and significant


def test_rq4_accepts_integer_zcta_cross_section(sample_panel_fixtures) -> None:
    """The real 35-column loader (``load_and_validate_data``) infers ZCTA5CE
    as i64, while the panel loaders pin Utf8. analyze_rq4 must normalize the
    cross-section key (zero-padded 5-char string) instead of crashing the
    join. Smoke-revealed on the first real PHX run (plan Task 20)."""
    cross, zp, lp, acs = sample_panel_fixtures
    cross_int = cross.with_columns(pl.col("ZCTA5CE").cast(pl.Int64))
    r_int = analyze_rq4(cross_int, zp, lp, acs)
    r_str = analyze_rq4(cross, zp, lp, acs)
    assert r_int.n_obs == r_str.n_obs
    assert r_int.n_zctas == r_str.n_zctas


def test_rq4_headline_uses_2019_vintage_not_2021(sample_panel_fixtures) -> None:
    """Fixture plants DIFFERENT 2019 and 2021 commute proxies; the headline
    interaction must load on the 2019 one (design §4: pre-treatment measurement)."""
    cross, zp, lp, acs = sample_panel_fixtures
    r = analyze_rq4(cross, zp, lp, acs)
    assert r.gradient_model_joint["x_vintage"] == "2019"
    assert "vintage2021" in r.vintage2021_robustness


def test_rq4_endpoint_trim_and_transition_drop(sample_panel_fixtures) -> None:
    cross, zp, lp, acs = sample_panel_fixtures
    r = analyze_rq4(cross, zp, lp, acs)
    assert r.n_post_months < zp["period"].n_unique()  # trim + drop actually removed months


def test_rq4_flags_thin_identification(sample_panel_fixtures_thin) -> None:
    """A fixture with 8 identifying ZCTAs must flag and carry bootstrap p."""
    cross, zp, lp, acs = sample_panel_fixtures_thin
    r = analyze_rq4(cross, zp, lp, acs)
    assert "under_identified" in r.flags
    assert "distance_to_cbd_km" in r.bootstrap_pvalues


# ---------------------------------------------------------------------------
# Renter-share-weighted Spec A robustness (design section 4 diagnostics:
# weights = renter_share x total_pop from the 35-column file)
# ---------------------------------------------------------------------------


def test_rq4_weighted_robustness_present_and_documented(
    sample_panel_fixtures,
) -> None:
    """The joint Spec A model carries a renter-share-weighted robustness
    entry (nested like transition_drop), with the weight spec and the
    weighted-estimand interpretation documented on the dict."""
    cross, zp, lp, acs = sample_panel_fixtures
    r = analyze_rq4(cross, zp, lp, acs)
    joint = r.gradient_model_joint

    weighted = joint["weighted_renter"]
    assert set(weighted["coefs"]) == set(GRADIENT_X_2019)
    for var in GRADIENT_X_2019:
        for key in ("post1_coef", "post1_se", "post1_pvalue",
                    "post2_coef", "post2_se", "post2_pvalue"):
            assert np.isfinite(weighted["coefs"][var][key])
    # same estimation sample as the headline joint model
    assert weighted["n_obs"] == joint["n_obs"]
    assert weighted["n_units"] == joint["n_units"]
    # weight spec follows the design section 4 wording exactly
    assert "renter_share" in weighted["weight_spec"]
    assert "total_pop" in weighted["weight_spec"]
    # estimand guidance: weighted = renter-prevalence-weighted repricing
    assert "renter" in weighted["estimand_note"].lower()
    assert "weight" in weighted["estimand_note"].lower()


def test_rq4_weighted_robustness_differs_from_unweighted(
    sample_panel_fixtures,
) -> None:
    """With genuinely varying renter weights the weighted estimand must not
    silently collapse to the unweighted one (a weights-ignored regression
    would make the two blocks identical)."""
    cross, zp, lp, acs = sample_panel_fixtures
    r = analyze_rq4(cross, zp, lp, acs)
    joint = r.gradient_model_joint
    unw = [
        joint["coefs"][v][f"{p}_coef"]
        for v in GRADIENT_X_2019 for p in ("post1", "post2")
    ]
    wtd = [
        joint["weighted_renter"]["coefs"][v][f"{p}_coef"]
        for v in GRADIENT_X_2019 for p in ("post1", "post2")
    ]
    assert not np.allclose(unw, wtd, rtol=1e-10, atol=0.0)


@pytest.mark.parametrize("bad_value", [0.0, float("nan")])
def test_rq4_weighted_degenerate_weights_raise_naming_zcta(
    sample_panel_fixtures, bad_value: float
) -> None:
    """A ZCTA with a zero/NaN renter weight must fail loudly BY NAME, not
    silently drop or propagate NaN into the weighted fit."""
    cross, zp, lp, acs = sample_panel_fixtures
    cross_bad = cross.with_columns(
        pl.when(pl.col("ZCTA5CE") == "85001")
        .then(pl.lit(bad_value))
        .otherwise(pl.col("renter_share"))
        .alias("renter_share")
    )
    with pytest.raises(ValueError, match="85001"):
        analyze_rq4(cross_bad, zp, lp, acs)


# ---------------------------------------------------------------------------
# Task 18: event study + Specs C / C-med / D
# ---------------------------------------------------------------------------


class TestEventTimeBins:
    """Bin-assignment grammar (design section 4, Spec B): event-time bins
    relative to 2020-03, NOT calendar years."""

    def test_2020_jan_feb_fall_in_base_bin(self) -> None:
        """Calendar-year bins would put pre-break 2020-01/02 into the treated
        bin; event-time bins must keep them in the base."""
        assert event_time_bin(date(2020, 1, 31)) == (0, "base")
        assert event_time_bin(date(2020, 2, 29)) == (0, "base")
        # base bin spans 2019-03 .. 2020-02
        assert event_time_bin(date(2019, 3, 31)) == (0, "base")
        assert event_time_bin(date(2019, 12, 31)) == (0, "base")

    def test_2020_march_starts_first_post_bin(self) -> None:
        assert event_time_bin(date(2020, 3, 31)) == (1, "post1")
        # 6-month post bins through 2022-02
        assert event_time_bin(date(2020, 8, 31)) == (1, "post1")
        assert event_time_bin(date(2020, 9, 30)) == (2, "post2")
        assert event_time_bin(date(2022, 2, 28)) == (4, "post4")

    def test_post_bins_widen_to_12_months_after_2022_02(self) -> None:
        assert event_time_bin(date(2022, 3, 31)) == (5, "post5")
        assert event_time_bin(date(2023, 2, 28)) == (5, "post5")
        assert event_time_bin(date(2023, 3, 31)) == (6, "post6")

    def test_pre_bins_count_back_12_months_from_base(self) -> None:
        assert event_time_bin(date(2019, 2, 28)) == (-1, "pre1")
        assert event_time_bin(date(2018, 3, 31)) == (-1, "pre1")
        assert event_time_bin(date(2018, 2, 28)) == (-2, "pre2")
        assert event_time_bin(date(2015, 3, 31)) == (-4, "pre4")

    def test_2015_jan_feb_fold_into_earliest_pre_bin(self) -> None:
        assert event_time_bin(date(2015, 1, 31)) == (-4, "pre4")
        assert event_time_bin(date(2015, 2, 28)) == (-4, "pre4")


def test_rq4_event_study_carries_per_bin_identifying_counts(
    sample_panel_fixtures,
) -> None:
    cross, zp, lp, acs = sample_panel_fixtures
    r = analyze_rq4(cross, zp, lp, acs)
    es = r.event_study

    required = {
        "variable", "bin", "bin_order", "coef", "se",
        "ci_lo", "ci_hi", "n_identifying",
    }
    assert required <= set(es.columns)
    assert es.height > 0
    assert (es["n_identifying"] > 0).all()

    # the base bin is present as the zero reference row, one per variable
    base = es.filter(pl.col("bin") == "base")
    assert base.height == len(GRADIENT_X_2019)
    assert (base["coef"] == 0.0).all()

    # the planted donut effect shows in the first post bin for distance
    d_post1 = es.filter(
        (pl.col("variable") == "distance_to_cbd_km") & (pl.col("bin") == "post1")
    )
    assert d_post1.height == 1
    assert d_post1["coef"][0] > 0


def test_rq4_spec_c_truncates_at_last_lodes_year(sample_panel_fixtures) -> None:
    """Spec C window ends at the last LODES year (2023-12): months beyond it
    must NOT enter estimation via carried-forward access values."""
    cross, zp, lp, acs = sample_panel_fixtures
    # extend the zori panel into 2024 (clone the 2023-12 rows) — LODES still
    # ends 2023, so these months have no access data to merge
    dec = zp.filter(pl.col("period") == "2023-12-31")
    extra = [
        dec.with_columns(pl.lit(iso).alias("period"))
        for iso in (
            "2024-01-31", "2024-02-29", "2024-03-31",
            "2024-04-30", "2024-05-31", "2024-06-30",
        )
    ]
    zp_extended = pl.concat([zp, *extra])

    r = analyze_rq4(cross, zp_extended, lp, acs)
    assert r.access_model["max_period"] == "2023-12-31"
    assert np.isfinite(r.access_model["theta"])
    assert np.isfinite(r.access_model["pvalue"])
    assert {"avg2yr", "drop_covid_years"} <= r.access_model["robustness"].keys()


def test_rq4_spec_d_drops_thin_annual_cells(sample_panel_fixtures) -> None:
    """Annual collapse requires >= MIN_MONTHS_PER_YEAR months per (i, y);
    plant a 5-month cell and assert it is dropped."""
    _cross, zp, _lp, _acs = sample_panel_fixtures
    zp_thin = zp.filter(
        ~(
            (pl.col("ZCTA5CE") == "85001")
            & (pl.col("period") >= "2021-06-01")
            & (pl.col("period") <= "2021-12-31")
        )
    )  # 85001 keeps only 2021-01..05 -> 5 months < 6
    frame = zp_thin.with_columns(
        pl.col("period").str.to_date("%Y-%m-%d").alias("period_date"),
        pl.col("zori").log().alias("log_zori"),
    )

    collapsed = collapse_annual(frame)

    planted = collapsed.filter(
        (pl.col("ZCTA5CE") == "85001") & (pl.col("year") == 2021)
    )
    assert planted.height == 0
    kept = collapsed.filter(
        (pl.col("ZCTA5CE") == "85001") & (pl.col("year") == 2020)
    )
    assert kept.height == 1
    assert (collapsed["n_months"] >= MIN_MONTHS_PER_YEAR).all()


def test_rq4_chase_models_lead_falsification_and_long_differences(
    sample_panel_fixtures,
) -> None:
    cross, zp, lp, acs = sample_panel_fixtures
    r = analyze_rq4(cross, zp, lp, acs)

    # lagged headline: predictive association, never causal
    assert np.isfinite(r.chase_model_lagged["phi"])
    assert r.chase_model_lagged["n_cells"] > 0
    # lead falsification model present, with the lead coefficient reported
    assert np.isfinite(r.chase_model_lead["phi_lead"])
    assert np.isfinite(r.chase_model_lead["pvalue_lead"])
    # contemporaneous variant
    assert np.isfinite(r.chase_model_contemp["phi"])

    # long differences keyed by window; the fixture has no 2015 rent data,
    # so 2015->2019 degrades to an insufficient-data note while 2019->2023
    # estimates on the incumbent ZCTAs
    assert set(r.long_difference) == {"2015_2019", "2019_2023"}
    assert "note" in r.long_difference["2015_2019"]
    assert np.isfinite(r.long_difference["2019_2023"]["coef"])
    assert r.long_difference["2019_2023"]["n_zctas"] > 0


# ---------------------------------------------------------------------------
# Task 19: run_analysis optional-import wiring + skip-when-panels-absent
# ---------------------------------------------------------------------------


def test_run_analysis_has_rq4_optional_import() -> None:
    """run_analysis mirrors the HAS_RQ2/HAS_RQ3 optional-import pattern."""
    import run_analysis

    assert run_analysis.HAS_RQ4 is True
    assert run_analysis.run_rq4 is not None


def test_run_analysis_skips_rq4_when_panels_absent(
    sample_zcta_csv: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A final-dir with only the 35-column CSV (old checkout / partial
    rebuild) must skip RQ4 with a log line and still succeed (exit 0):
    RQ1-RQ3 run unaffected and no rq4 summary is written."""
    import run_analysis

    out_base = tmp_path / "out"
    fig_base = tmp_path / "fig"
    with caplog.at_level(logging.INFO, logger="run_analysis"):
        # .fn bypasses the Prefect engine; the body is the wiring under test
        ok, msg = run_analysis.analyze_metro_flow.fn(
            "PHX", sample_zcta_csv.parent, out_base, fig_base, None
        )

    assert ok, msg
    skip_lines = [
        r.message
        for r in caplog.records
        if "RQ4" in r.message and "skip" in r.message.lower()
    ]
    assert skip_lines, "no RQ4 skip log line emitted"
    # RQ1-RQ3 outputs exist; the RQ4 summary does not
    assert (out_base / "PHX" / "analysis_summary_phx.md").exists()
    assert not (out_base / "PHX" / "rq4_summary_PHX.md").exists()


def test_rq4_mediation_share_bounded_and_labeled(sample_panel_fixtures) -> None:
    """Spec C-med: share of Post1 repricing absorbed by contemporaneous
    access — labeled mediation, never robustness."""
    cross, zp, lp, acs = sample_panel_fixtures
    r = analyze_rq4(cross, zp, lp, acs)

    assert -1.5 <= r.mediation["share_mediated"] <= 1.5
    assert "mediation" in r.mediation["label"].lower()
    assert "robust" not in r.mediation["label"].lower()
    # per-variable shares for the full headline set
    assert set(r.mediation["share_by_x"]) == set(GRADIENT_X_2019)


# ---------------------------------------------------------------------------
# Issue #19: repricing consumed vs. the pre-COVID commute discount
# ---------------------------------------------------------------------------


class TestPhaseMonthCounts:
    """Post1 is fixed at its full window; Post2 counts to the panel end."""

    def test_post1_is_fixed_at_22_months(self) -> None:
        counts = phase_month_counts(date(2026, 5, 31))
        assert counts["post1"] == 22

    def test_post2_counts_2022_01_through_panel_end_inclusive(self) -> None:
        counts = phase_month_counts(date(2026, 5, 31))
        assert counts["post2"] == 53  # 2022-01 .. 2026-05 inclusive

    def test_post2_single_month(self) -> None:
        counts = phase_month_counts(date(2022, 1, 31))
        assert counts["post2"] == 1


class TestCumulativeRepricing:
    """Hand-computed accumulation arithmetic: phase months x coefficient."""

    def test_hand_computed_accumulation(self) -> None:
        # Denver-shaped numbers from docs/findings.md §10 Spec A.
        phase_months = {"post1": 22, "post2": 53}
        result = cumulative_repricing(0.0056, 0.0076, phase_months)
        assert result == pytest.approx(0.0056 * 22 + 0.0076 * 53)
        assert result == pytest.approx(0.5260, abs=1e-4)

    def test_zero_coefficients_accumulate_to_zero(self) -> None:
        assert cumulative_repricing(0.0, 0.0, {"post1": 22, "post2": 53}) == 0.0

    def test_negative_post1_coefficient_reduces_cumulative(self) -> None:
        phase_months = {"post1": 10, "post2": 5}
        result = cumulative_repricing(-0.001, 0.002, phase_months)
        assert result == pytest.approx(-0.001 * 10 + 0.002 * 5)
        assert result == pytest.approx(0.0, abs=1e-9)


class TestIsSignificantRepricing:
    """Both-phase gate: Post1 AND Post2 must clear p < 0.05."""

    @staticmethod
    def _coefs(post1_pvalue: float, post2_pvalue: float) -> dict[str, float]:
        return {
            "post1_coef": 0.01, "post1_se": 0.001, "post1_pvalue": post1_pvalue,
            "post2_coef": 0.01, "post2_se": 0.001, "post2_pvalue": post2_pvalue,
        }

    def test_both_significant(self) -> None:
        assert is_significant_repricing(self._coefs(0.01, 0.02)) is True

    def test_only_post1_significant(self) -> None:
        assert is_significant_repricing(self._coefs(0.01, 0.5)) is False

    def test_only_post2_significant(self) -> None:
        assert is_significant_repricing(self._coefs(0.5, 0.01)) is False

    def test_neither_significant(self) -> None:
        assert is_significant_repricing(self._coefs(0.5, 0.6)) is False

    def test_boundary_p_equals_alpha_is_not_significant(self) -> None:
        assert is_significant_repricing(self._coefs(0.05, 0.01)) is False


class TestClosingProjection:
    """Naive linear projection of the closing date — never a forecast."""

    def test_already_consumed_when_cumulative_exceeds_discount(self) -> None:
        result = closing_projection(0.02, 0.03, 0.001, date(2026, 5, 31))
        assert result["status"] == "already_consumed"

    def test_already_consumed_at_exact_equality(self) -> None:
        result = closing_projection(0.02, 0.02, 0.001, date(2026, 5, 31))
        assert result["status"] == "already_consumed"

    def test_not_closing_when_post2_rate_is_negative(self) -> None:
        result = closing_projection(0.02, 0.01, -0.0005, date(2026, 5, 31))
        assert result["status"] == "not_closing"

    def test_not_closing_when_post2_rate_is_zero(self) -> None:
        result = closing_projection(0.02, 0.01, 0.0, date(2026, 5, 31))
        assert result["status"] == "not_closing"

    def test_projected_close_date_hand_computed(self) -> None:
        # remaining = 0.02 - 0.01 = 0.01; rate 0.002/month -> 5 months
        result = closing_projection(0.02, 0.01, 0.002, date(2026, 5, 31))
        assert result["status"] == "projected"
        assert result["months_needed"] == pytest.approx(5.0)
        assert result["projected_close_date"] == "2026-10-31"

    def test_projected_close_date_rounds_up_fractional_months(self) -> None:
        # remaining = 0.015; rate 0.01/month -> 1.5 months -> rounds up to 2
        result = closing_projection(0.02, 0.005, 0.01, date(2026, 5, 31))
        assert result["status"] == "projected"
        assert result["months_needed"] == pytest.approx(1.5)
        assert result["projected_close_date"] == "2026-07-31"


class TestRepricingConsumedComposition:
    """_repricing_consumed composes the gate, accumulation, and projection."""

    @staticmethod
    def _precovid(coef: float = -0.02) -> dict[str, float]:
        return {"coef": coef, "se": 0.002, "pvalue": 0.001, "n_zctas": 50}

    def test_insignificant_metro_reports_null_note(self) -> None:
        coefs = {
            "post1_coef": 0.001, "post1_se": 0.002, "post1_pvalue": 0.6,
            "post2_coef": 0.001, "post2_se": 0.002, "post2_pvalue": 0.7,
        }
        result = _repricing_consumed(
            self._precovid(), coefs, {"post1": 22, "post2": 53}, date(2026, 5, 31)
        )
        assert result["significant"] is False
        assert "note" in result
        assert "cumulative_repricing" not in result
        assert "share_consumed" not in result

    def test_significant_metro_reports_share_and_projection(self) -> None:
        coefs = {
            "post1_coef": 0.0056, "post1_se": 0.001, "post1_pvalue": 0.0001,
            "post2_coef": 0.0076, "post2_se": 0.001, "post2_pvalue": 0.0001,
        }
        phase_months = {"post1": 22, "post2": 53}
        result = _repricing_consumed(
            self._precovid(coef=-1.0), coefs, phase_months, date(2026, 5, 31)
        )
        assert result["significant"] is True
        expected_cumulative = cumulative_repricing(0.0056, 0.0076, phase_months)
        assert result["cumulative_repricing"] == pytest.approx(expected_cumulative)
        assert result["share_consumed"] == pytest.approx(expected_cumulative / 1.0)
        assert result["projection"]["status"] == "projected"

    def test_zero_precovid_gradient_yields_no_discount_note(self) -> None:
        coefs = {
            "post1_coef": 0.0056, "post1_se": 0.001, "post1_pvalue": 0.0001,
            "post2_coef": 0.0076, "post2_se": 0.001, "post2_pvalue": 0.0001,
        }
        result = _repricing_consumed(
            self._precovid(coef=0.0), coefs, {"post1": 22, "post2": 53},
            date(2026, 5, 31),
        )
        assert result["share_consumed"] is None
        assert result["projection"]["status"] == "no_precovid_discount"
        # (b) still reports even when (c)/(d) are withheld
        assert np.isfinite(result["cumulative_repricing"])

    def test_positive_insignificant_precovid_gradient_yields_no_discount_note(
        self,
    ) -> None:
        """A Phoenix-shaped case: the 2019 cross-sectional gradient is small,
        positive, and insignificant (p = 0.17) — no real discount exists to
        divide cumulative repricing into, even though commute x Post1/Post2
        both clear the repricing significance gate."""
        coefs = {
            "post1_coef": 0.0037, "post1_se": 0.001, "post1_pvalue": 0.01,
            "post2_coef": 0.0048, "post2_se": 0.001, "post2_pvalue": 0.01,
        }
        result = _repricing_consumed(
            self._precovid(coef=0.005), coefs, {"post1": 22, "post2": 53},
            date(2026, 5, 31),
        )
        assert result["significant"] is True
        assert result["share_consumed"] is None
        assert result["projection"]["status"] == "no_precovid_discount"


def test_rq4_repricing_consumed_gate_matches_significance(
    sample_panel_fixtures,
) -> None:
    """analyze_rq4's repricing_consumed field must agree with
    is_significant_repricing on whatever the fixture's collinearity actually
    produces for the commute regressor (the fixture only plants a
    distance_to_cbd_km effect, not a commute one, so the outcome is not
    hardcoded here — see plan Task 20 note)."""
    cross, zp, lp, acs = sample_panel_fixtures
    r = analyze_rq4(cross, zp, lp, acs)
    rc = r.repricing_consumed
    commute_coefs = r.gradient_model_joint["coefs"]["commute_min_proxy_2019"]

    assert rc["significant"] == is_significant_repricing(commute_coefs)
    assert "precovid_gradient" in rc
    assert np.isfinite(rc["precovid_gradient"]["coef"])
    assert rc["phase_months"]["post1"] == 22
    assert rc["phase_months"]["post2"] > 0

    if rc["significant"]:
        assert np.isfinite(rc["cumulative_repricing"])
        assert rc["share_consumed"] is None or np.isfinite(rc["share_consumed"])
        assert rc["projection"]["status"] in {
            "already_consumed", "not_closing", "projected",
            "no_precovid_discount",
        }
    else:
        assert "note" in rc
