"""Tests for the provenance manifest."""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

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
    # Build path unchanged (issue #3): default provenance is pipeline-build,
    # the build commit is populated, and no regeneration commit is claimed.
    assert m["provenance"] == "pipeline-build"
    assert m["git_commit"] == "abc123"
    assert m["regenerated_at_commit"] is None
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


def test_build_manifest_regenerated_offline_never_claims_build_commit(tmp_path: Path) -> None:
    """Issue #3: offline regeneration must not stamp the current commit as build provenance.

    Even though the caller passes the stamping commit, the manifest records
    git_commit=null and moves the stamping commit to regenerated_at_commit.
    """
    csv = _tiny_csv(tmp_path)
    m = build_manifest(
        "test", csv, git_commit="deadbeef", timestamp_utc="2026-07-17T00:00:00Z",
        zori_period="2024-01-31", steps=[], provenance="regenerated-offline",
    )
    assert m["provenance"] == "regenerated-offline"
    assert m["git_commit"] is None
    assert m["regenerated_at_commit"] == "deadbeef"
    # Backward-compatible field names survive the mode switch.
    assert m["zori_period"] == "2024-01-31"
    assert m["lodes_year"] == 2021
    assert "zori" in m["source_urls"]
    assert len(m["sha256"]) == 64


def test_manifest_records_cbsa_vintage_in_both_provenance_modes(tmp_path: Path) -> None:
    """Issue #2: the pinned CBSA delineation vintage is stamped into manifests.

    TIGERweb reorders MapServer layer ids; the manifest must say which
    delineation vintage the CBSA polygon came from, in both provenance modes.
    """
    from src.pipelines.tiger import CBSA_VINTAGE

    csv = _tiny_csv(tmp_path)
    built = build_manifest(
        "test", csv, git_commit="abc", timestamp_utc="t", zori_period=None, steps=[],
    )
    regenerated = build_manifest(
        "test", csv, git_commit="abc", timestamp_utc="t", zori_period=None, steps=[],
        provenance="regenerated-offline",
    )
    assert built["cbsa_vintage"] == CBSA_VINTAGE == "ACS 2024"
    assert regenerated["cbsa_vintage"] == "ACS 2024"


def test_build_manifest_rejects_unknown_provenance(tmp_path: Path) -> None:
    csv = _tiny_csv(tmp_path)
    with pytest.raises(ValueError, match="provenance"):
        build_manifest(
            "test", csv, git_commit="abc", timestamp_utc="t",
            zori_period=None, steps=[], provenance="hand-edited",
        )


def test_generate_manifests_offline_path_records_regenerated_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The actual --generate-manifests path threads the offline mode through.

    Exercises run_pipeline.generate_manifests_offline() against a temp
    DATA_FINAL holding one real metro's CSV: the written manifest must carry
    provenance=regenerated-offline, a null git_commit, and the stamping commit
    in regenerated_at_commit (issue #3).
    """
    import run_pipeline
    import src.pipelines.config as config
    import src.pipelines.manifest as manifest_mod

    csv = tmp_path / "final_zcta_dataset_phoenix.csv"
    pl.DataFrame(
        {"ZCTA5CE": ["85001"], "period": ["2024-01-31"], "rent_to_income": [0.3]}
    ).write_csv(csv)
    monkeypatch.setattr(config, "DATA_FINAL", tmp_path)
    monkeypatch.setattr(manifest_mod, "get_git_commit", lambda: "cafe1234")

    assert run_pipeline.generate_manifests_offline() == 0

    written = json.loads((tmp_path / "phoenix.manifest.json").read_text())
    assert written["provenance"] == "regenerated-offline"
    assert written["git_commit"] is None
    assert written["regenerated_at_commit"] == "cafe1234"
    # Backward-compatible fields still populated by the offline path.
    assert written["zori_period"] == "2024-01-31"
    assert written["metro_config"] is not None
    assert written["metro_config"]["cbsa_code"] == "38060"
    assert written["row_count"] == 1
