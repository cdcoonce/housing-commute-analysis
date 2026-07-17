"""Tests for scripts/rebuild_gate.py (loaded via importlib — scripts/ is not a package)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

_SPEC = importlib.util.spec_from_file_location(
    "rebuild_gate",
    Path(__file__).resolve().parents[1] / "scripts" / "rebuild_gate.py",
)
rebuild_gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rebuild_gate)


def _write_csv(path: Path, rows: list[dict]) -> Path:
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _row(zcta: str, income: float = 50000.0) -> dict:
    return {
        "ZCTA5CE": zcta,
        "median_income": income,
        "income_segment": "Medium",
        "zori": 1500.0,
        "stops_per_km2": 1.0,
        "period": "2026-06",
        "job_density": 100.0,
        "distance_to_cbd_km": 2.0,
        "job_accessibility": 50000.0,
    }


def test_check_metro_reports_duplicate_rows_instead_of_crashing(tmp_path) -> None:
    """Equal ZCTA sets but unequal row counts (duplicated ZCTA5CE rows) must
    produce a gate FAILURE naming the duplication — not a ValueError from the
    element-wise frozen-column comparison (the memphis crash)."""
    base = _write_csv(
        tmp_path / "base.csv",
        [_row("38103"), _row("38104", income=60000.0)],
    )
    new = _write_csv(
        tmp_path / "new.csv",
        [_row("38103"), _row("38103"), _row("38104", income=60000.0)],
    )
    errors = rebuild_gate.check_metro(base, new, accept_drift=set())
    assert any("duplicated ZCTA5CE" in e for e in errors), errors
