"""Tests for the report_rq* I/O half and save_markdown_table."""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from src.models.reporting import save_markdown_table
from src.models.rq1_housing_commute_tradeoff import analyze_rq1, report_rq1
from src.models.rq2_equity_analysis import analyze_rq2, report_rq2
from src.models.rq3_aci_analysis import analyze_rq3, report_rq3
from src.models.rq4_rent_dynamics import analyze_rq4, report_rq4


def _dirs(tmp_path: Path) -> tuple[Path, Path]:
    out = tmp_path / "out"
    fig = tmp_path / "fig"
    out.mkdir()
    fig.mkdir()
    return out, fig


def test_report_rq1_writes_summary_csv_and_figures(sample_zcta_df: pl.DataFrame, tmp_path: Path) -> None:
    out, fig = _dirs(tmp_path)
    report_rq1(analyze_rq1(sample_zcta_df), out, fig, "PHX")
    md = out / "analysis_summary_phx.md"
    assert md.exists()
    text = md.read_text()
    assert "Model Comparison" in text
    assert (out / "rq1_model_data_phx.csv").exists()
    for name in ("rq1_phx_scatter.png", "rq1_phx_residuals.png", "rq1_phx_qq.png", "rq1_phx_hist.png"):
        assert (fig / name).exists()


def test_report_rq2_appends_to_summary(sample_zcta_df: pl.DataFrame, tmp_path: Path) -> None:
    out, fig = _dirs(tmp_path)
    report_rq1(analyze_rq1(sample_zcta_df), out, fig, "PHX")  # header author first
    report_rq2(analyze_rq2(sample_zcta_df), out, fig, "PHX")
    assert (out / "analysis_summary_phx.md").exists()


def test_report_rq3_appends_to_summary(sample_zcta_df: pl.DataFrame, tmp_path: Path) -> None:
    out, fig = _dirs(tmp_path)
    report_rq1(analyze_rq1(sample_zcta_df), out, fig, "PHX")
    report_rq3(analyze_rq3(sample_zcta_df), out, fig, "PHX")
    assert (out / "analysis_summary_phx.md").exists()


def test_report_rq4_writes_summary_with_caveats_and_figures(
    sample_panel_fixtures, tmp_path: Path
) -> None:
    """report_rq4 writes rq4_summary_<metro>.md with the mandatory honesty
    rails (design section 4 caveats + section 6) and the event-study figure."""
    out, fig = _dirs(tmp_path)
    cross, zp, lp, acs = sample_panel_fixtures
    report_rq4(analyze_rq4(cross, zp, lp, acs), out, fig, "PHX")

    md = out / "rq4_summary_PHX.md"
    assert md.exists()
    text = md.read_text()

    # mandatory caveats block — grep anchors from plan Task 19
    assert "not a causal" in text
    assert "covered-ZCTA" in text
    assert "listing" in text
    # the estimand statement and the remaining caveat families
    assert "ZCTA" in text and "ZIP" in text  # ZIP~ZCTA convention named
    assert "sorting" in text.lower() or "composition" in text.lower()

    # coefficient/Wald/bootstrap tables present (phase 1/2 + pooled)
    assert "post1" in text.lower() or "phase 1" in text.lower()
    assert "Wald" in text
    assert "bootstrap" in text.lower()
    assert "Entrant" in text or "entrant" in text

    # figures: event study (with per-bin identifying counts) + phase coefs
    assert (fig / "rq4_phx_event_study.png").exists()
    assert (fig / "rq4_phx_gradient_phases.png").exists()

    # renter-share-weighted Spec A robustness: clearly-labeled table with the
    # design section 4 weight spec and one-line estimand guidance, while the
    # unweighted estimand honesty rail stays verbatim
    assert "renter-share-weighted" in text
    assert "renter_share" in text and "total_pop" in text
    assert "renter-prevalence-weighted" in text
    assert "not renter-weighted" in text  # existing estimand rail intact


def test_save_markdown_table_writes_heading(tmp_path: Path) -> None:
    p = tmp_path / "t.md"
    save_markdown_table({"A": [1, 2], "B": [3, 4]}, p, "My Title")
    txt = p.read_text()
    assert "### My Title" in txt
    assert "A" in txt and "B" in txt


def test_save_markdown_table_length_mismatch_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        save_markdown_table({"A": [1, 2], "B": [3]}, tmp_path / "t.md", "T")
