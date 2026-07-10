"""Tests for the report_rq* I/O half and save_markdown_table."""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from src.models.reporting import save_markdown_table
from src.models.rq1_housing_commute_tradeoff import analyze_rq1, report_rq1
from src.models.rq2_equity_analysis import analyze_rq2, report_rq2
from src.models.rq3_aci_analysis import analyze_rq3, report_rq3


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


def test_save_markdown_table_writes_heading(tmp_path: Path) -> None:
    p = tmp_path / "t.md"
    save_markdown_table({"A": [1, 2], "B": [3, 4]}, p, "My Title")
    txt = p.read_text()
    assert "### My Title" in txt
    assert "A" in txt and "B" in txt


def test_save_markdown_table_length_mismatch_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        save_markdown_table({"A": [1, 2], "B": [3]}, tmp_path / "t.md", "T")
