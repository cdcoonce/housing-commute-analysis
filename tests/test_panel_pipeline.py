"""Offline tests for the RQ4 panel pipeline (monkeypatched HTTP throughout)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import src.pipelines.zori as zori

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def zori_wide() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "zori_wide_fixture.csv")


def _patch_http(monkeypatch, wide: pd.DataFrame) -> None:
    monkeypatch.setattr(zori, "http_csv_to_df", lambda url: wide.copy())


def test_tidy_zori_long_shape(zori_wide) -> None:
    out = zori.tidy_zori(zori_wide)
    assert list(out.columns) == ["zip", "period", "zori"]
    assert out["zip"].str.len().eq(5).all()          # zero-padded
    assert out["zori"].notna().all()                  # MA + NaN cells dropped
    assert not out.duplicated(["zip", "period"]).any()


def test_fetch_zori_latest_byte_identical_to_golden(monkeypatch, zori_wide) -> None:
    """The tidy_zori refactor must not change fetch_zori_latest by one byte —
    fetch_zori_task's TASK_SOURCE cache key survives only because build.py's
    wrapper body is untouched; this pins the *output* too."""
    _patch_http(monkeypatch, zori_wide)
    got = zori.fetch_zori_latest("fixture://").to_csv(index=False)
    golden = (FIXTURES / "zori_latest_golden.csv").read_text()
    assert got == golden


def test_tidy_zori_tail_equals_latest(monkeypatch, zori_wide) -> None:
    """Same-pull consistency: last row per zip of the tidy frame == latest frame."""
    _patch_http(monkeypatch, zori_wide)
    latest = zori.fetch_zori_latest("fixture://").reset_index(drop=True)
    tail = (
        zori.tidy_zori(zori_wide)
        .sort_values(["zip", "period"]).groupby("zip", as_index=False).tail(1)
        [["zip", "period", "zori"]].reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(tail, latest)


def test_fetch_zori_series_prefix_filter(monkeypatch, zori_wide) -> None:
    _patch_http(monkeypatch, zori_wide)
    out = zori.fetch_zori_series("fixture://", ("850", "851"))
    assert set(out.columns) == {"zip", "period", "zori"}
    assert out["zip"].str[:3].isin({"850", "851"}).all()
    assert "38103" not in set(out["zip"])            # non-matching ZIP excluded
    # stable-sorted for deterministic committed bytes (issue #6 convention)
    assert out.equals(out.sort_values(["zip", "period"], kind="stable", ignore_index=True))


def test_zori_panel_url_is_non_sa() -> None:
    from src.pipelines.config import ZORI_PANEL_CSV_URL, ZORI_ZIP_CSV_URL
    assert ZORI_PANEL_CSV_URL.endswith("_sm_month.csv")        # no _sa_
    assert ZORI_ZIP_CSV_URL.endswith("_sm_sa_month.csv")       # cross-sectional untouched
