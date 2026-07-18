"""Tests for RQ4 (ZORI rent dynamics): results contract and panel fixtures.

Task 16 scope: the frozen RQ4Results container and the synthetic
sample_panel_fixtures quadruple that feeds the analysis tests (Tasks 17-19).
"""
from __future__ import annotations

import dataclasses
from datetime import date

import polars as pl
import pytest

from src.models.results import RQ4Results
from src.pipelines.schema import (
    validate_acs_commute_2019,
    validate_lodes_panel,
    validate_zori_panel,
)

BREAK_MONTH = date(2020, 3, 31)
POST2_START = date(2022, 1, 31)


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
