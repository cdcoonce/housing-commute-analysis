"""Tests for the provenance manifest."""
from __future__ import annotations

from pathlib import Path

import polars as pl

from src.pipelines.manifest import build_manifest, verify_manifest, write_manifest


def _tiny_csv(tmp_path: Path) -> Path:
    p = tmp_path / "final_zcta_dataset_test.csv"
    pl.DataFrame({"ZCTA5CE": ["00001"], "period": ["2024-01-31"], "rent_to_income": [0.3]}).write_csv(p)
    return p


def test_build_manifest_fields(tmp_path: Path) -> None:
    csv = _tiny_csv(tmp_path)
    m = build_manifest(
        "test", csv, git_commit="abc123", timestamp_utc="2026-07-09T00:00:00Z",
        zori_period="2024-01-31", steps=[{"name": "fetch_acs", "status": "completed", "duration_s": 1.0}],
    )
    assert m["metro_key"] == "test"
    assert m["git_commit"] == "abc123"
    assert m["acs_commute_year"] == 2021
    assert m["acs_demographics_year"] == 2023
    assert m["row_count"] == 1
    assert len(m["sha256"]) == 64
    # Note: polars infers Int64 for the all-numeric ZCTA5CE column in this tiny
    # synthetic CSV ("00001" -> 1), not String. Calibrated to the observed dtype
    # per task-3.3-brief.md Step 3 guidance; do not force String via source changes.
    assert {"name": "ZCTA5CE", "dtype": "Int64"} in m["columns"]


def test_verify_manifest_clean_then_drift(tmp_path: Path) -> None:
    csv = _tiny_csv(tmp_path)
    m = build_manifest("test", csv, git_commit="x", timestamp_utc="t", zori_period=None, steps=[])
    mpath = tmp_path / "test.manifest.json"
    write_manifest(m, mpath)
    assert verify_manifest(csv, mpath) == []          # clean
    pl.DataFrame({"ZCTA5CE": ["00001", "00002"], "period": ["a", "b"], "rent_to_income": [0.1, 0.2]}).write_csv(csv)
    assert verify_manifest(csv, mpath)                 # drift detected


def test_build_manifest_records_metro_config(tmp_path: Path) -> None:
    """A known metro's config essentials are embedded, JSON-serializable (tuples -> lists)."""
    import json

    from src.pipelines.config import METRO_CONFIGS

    csv = _tiny_csv(tmp_path)
    m = build_manifest(
        "phoenix", csv, git_commit="abc", timestamp_utc="2026-07-16T00:00:00Z",
        zori_period=None, steps=[],
    )
    mc = m["metro_config"]
    assert mc is not None
    assert mc["cbsa_code"] == "38060"
    assert mc["utm_zone"] == 32612
    assert mc["counties"] == [list(c) for c in METRO_CONFIGS["phoenix"]["counties"]]
    assert mc["zip_prefixes"] == METRO_CONFIGS["phoenix"]["zip_prefixes"]
    assert mc["cbd_points"] == [list(p) for p in METRO_CONFIGS["phoenix"]["cbd_points"]]
    # No tuples anywhere: must round-trip through strict JSON unchanged.
    assert json.loads(json.dumps(mc)) == mc


def test_build_manifest_unknown_metro_config_is_null(tmp_path: Path) -> None:
    """Metros absent from METRO_CONFIGS (e.g. the 'test' metro) yield null, not a raise."""
    csv = _tiny_csv(tmp_path)
    m = build_manifest(
        "test", csv, git_commit="abc", timestamp_utc="2026-07-16T00:00:00Z",
        zori_period=None, steps=[],
    )
    assert m["metro_config"] is None


def test_manifest_includes_lodes_provenance(tmp_path) -> None:
    import polars as pl

    from src.pipelines.manifest import build_manifest

    csv = tmp_path / "final_zcta_dataset_test.csv"
    pl.DataFrame({"ZCTA5CE": [85001]}).write_csv(csv)
    m = build_manifest(
        "test", csv, git_commit="abc", timestamp_utc="2026-01-01T00:00:00+00:00",
        zori_period=None, steps=[],
    )
    assert m["lodes_year"] == 2021
    assert "lodes" in m["source_urls"]
    assert "LODES8" in m["source_urls"]["lodes"]
