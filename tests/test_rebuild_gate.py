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


def test_check_metro_accepts_named_drift_column(tmp_path, capsys) -> None:
    """accept_drift excludes the named column from the frozen byte-identity
    check and reports the differing row count instead of failing the gate."""
    base = _write_csv(
        tmp_path / "base.csv",
        [_row("98338"), _row("98409", income=60000.0)],
    )
    changed = _row("98338")
    changed["median_income"] = 50100.0  # 0.2% — real drift, but accepted
    new = _write_csv(tmp_path / "new.csv", [changed, _row("98409", income=60000.0)])

    errors = rebuild_gate.check_metro(base, new, accept_drift={"median_income"})

    assert not any("median_income" in e for e in errors), errors
    assert "accepted drift median_income: 1 rows differ" in capsys.readouterr().out


def test_verify_income_segment_drift_passes_when_boundaries_disagree() -> None:
    """The boundary proof compares each side against its own quantile rule
    independently, so it still passes even when tercile and quartile
    boundaries assign different segments to some ZCTAs."""
    incomes = ["30000", "40000", "45000", "50000", "90000"]
    correct_quartile = ["Low", "Medium", "Medium", "Medium", "High"]
    correct_tercile = ["Low", "Low", "Medium", "High", "High"]
    base = pd.DataFrame({"median_income": incomes, "income_segment": correct_quartile})
    new = pd.DataFrame({"median_income": incomes, "income_segment": correct_tercile})

    assert base["income_segment"].tolist() != new["income_segment"].tolist()
    assert rebuild_gate.verify_income_segment_drift(base, new) == []


def test_verify_income_segment_drift_reports_isolated_failures() -> None:
    """Each recomputation is checked independently: a wrong NEW segment only
    trips the tercile error, a wrong BASELINE segment only trips the
    quartile error."""
    incomes = ["30000", "40000", "45000", "50000", "90000"]
    correct_quartile = ["Low", "Medium", "Medium", "Medium", "High"]
    correct_tercile = ["Low", "Low", "Medium", "High", "High"]

    base_ok = pd.DataFrame({"median_income": incomes, "income_segment": correct_quartile})
    new_wrong = pd.DataFrame(
        {"median_income": incomes, "income_segment": ["High", "Low", "Medium", "High", "High"]}
    )
    errors = rebuild_gate.verify_income_segment_drift(base_ok, new_wrong)
    assert len(errors) == 1
    assert sum("tercile recomputation from NEW" in e for e in errors) == 1

    base_wrong = pd.DataFrame(
        {"median_income": incomes, "income_segment": ["High", "Medium", "Medium", "Medium", "High"]}
    )
    new_ok = pd.DataFrame({"median_income": incomes, "income_segment": correct_tercile})
    errors = rebuild_gate.verify_income_segment_drift(base_wrong, new_ok)
    assert len(errors) == 1
    assert sum("quartile recomputation from BASELINE" in e for e in errors) == 1


def test_check_metro_fails_on_negative_job_density(tmp_path) -> None:
    """job_density < 0 fails the gate when the other two sanity checks stay
    quiet (a ZCTA near the CBD, accessibility falling with distance)."""
    rows = [
        {**_row("10001"), "job_density": -5.0, "distance_to_cbd_km": 1.0, "job_accessibility": 90000.0},
        {**_row("10002"), "distance_to_cbd_km": 2.0, "job_accessibility": 50000.0},
        {**_row("10003"), "distance_to_cbd_km": 5.0, "job_accessibility": 10000.0},
    ]
    base = _write_csv(tmp_path / "base.csv", rows)
    new = _write_csv(tmp_path / "new.csv", rows)

    errors = rebuild_gate.check_metro(base, new, accept_drift=set())

    assert len(errors) == 1
    assert "job_density has negative values" in errors[0]


def test_check_metro_fails_when_no_zcta_near_cbd(tmp_path) -> None:
    """min(distance_to_cbd_km) >= 3.0 fails the gate when the other two
    sanity checks stay quiet (non-negative job_density, accessibility
    falling with distance)."""
    rows = [
        {**_row("10001"), "distance_to_cbd_km": 3.0, "job_accessibility": 90000.0},
        {**_row("10002"), "distance_to_cbd_km": 5.0, "job_accessibility": 50000.0},
        {**_row("10003"), "distance_to_cbd_km": 9.0, "job_accessibility": 10000.0},
    ]
    base = _write_csv(tmp_path / "base.csv", rows)
    new = _write_csv(tmp_path / "new.csv", rows)

    errors = rebuild_gate.check_metro(base, new, accept_drift=set())

    assert len(errors) == 1
    assert "min distance_to_cbd_km" in errors[0]


def test_check_metro_fails_when_accessibility_rises_with_distance(tmp_path) -> None:
    """A positive Spearman correlation between job_accessibility and
    distance_to_cbd_km fails the gate when the other two sanity checks stay
    quiet (non-negative job_density, a ZCTA near the CBD)."""
    rows = [
        {**_row("10001"), "distance_to_cbd_km": 1.0, "job_accessibility": 10000.0},
        {**_row("10002"), "distance_to_cbd_km": 4.0, "job_accessibility": 50000.0},
        {**_row("10003"), "distance_to_cbd_km": 9.0, "job_accessibility": 90000.0},
    ]
    base = _write_csv(tmp_path / "base.csv", rows)
    new = _write_csv(tmp_path / "new.csv", rows)

    errors = rebuild_gate.check_metro(base, new, accept_drift=set())

    assert len(errors) == 1
    assert "job_accessibility does not fall with CBD distance" in errors[0]
