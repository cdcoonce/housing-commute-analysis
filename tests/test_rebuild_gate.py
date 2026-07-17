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


def test_check_metro_tolerates_float_noise_but_fails_real_drift(tmp_path) -> None:
    """A last-ULP float difference in a frozen numeric column (summation-order
    noise, ~1e-16 relative) must not fail the gate — but a real value change
    (>> 1e-12 relative) must."""
    base = _write_csv(
        tmp_path / "base.csv",
        [_row("98338"), _row("98409", income=60000.0)],
    )
    noise = _row("98338")
    noise["median_income"] = 50000.000000000007  # ULP-level
    new_noise = _write_csv(tmp_path / "new_noise.csv", [noise, _row("98409", income=60000.0)])
    errors = rebuild_gate.check_metro(base, new_noise, accept_drift=set())
    assert not any("median_income" in e for e in errors), errors

    real = _row("98338")
    real["median_income"] = 50100.0  # 0.2% — real drift
    new_real = _write_csv(tmp_path / "new_real.csv", [real, _row("98409", income=60000.0)])
    errors = rebuild_gate.check_metro(base, new_real, accept_drift=set())
    assert any("median_income" in e for e in errors), errors


def test_check_metro_still_fails_non_numeric_frozen_drift(tmp_path) -> None:
    """String-typed frozen columns keep strict byte-identity."""
    base = _write_csv(tmp_path / "base.csv", [_row("98338"), _row("98409")])
    changed = _row("98338")
    changed["income_segment"] = "High"
    new = _write_csv(tmp_path / "new.csv", [changed, _row("98409")])
    errors = rebuild_gate.check_metro(base, new, accept_drift=set())
    assert any("income_segment" in e for e in errors), errors


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
