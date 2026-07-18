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
    analyze_rq4,
    collapse_annual,
    event_time_bin,
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
