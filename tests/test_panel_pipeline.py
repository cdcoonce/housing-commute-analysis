"""Offline tests for the RQ4 panel pipeline (monkeypatched HTTP throughout)."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

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


def test_zori_panel_task_renames_filters_sorts() -> None:
    """zori_panel_task.fn: zip->ZCTA5CE rename, inner-filter to the metro ZCTA
    set, stable-sort by (ZCTA5CE, period). Called via .fn to bypass the runner.
    """
    from src.pipelines.panel import zori_panel_task

    zori_long = pd.DataFrame(
        {
            "zip": ["85002", "85002", "85001", "85001", "38103", "85099"],
            "period": [
                "2020-02-29", "2020-01-31", "2020-02-29", "2020-01-31",
                "2020-01-31", "2020-01-31",
            ],
            "zori": [1210.0, 1200.0, 1510.0, 1500.0, 900.0, 1000.0],
        }
    )
    # The task only touches the ZCTA5CE column, so a plain frame stands in for
    # the zctas_in_metro GeoDataFrame. 38103/85099 are absent -> filtered out.
    zctas_in_metro = pd.DataFrame({"ZCTA5CE": ["85001", "85002"]})

    out = zori_panel_task.fn(zori_long, zctas_in_metro)

    assert list(out.columns) == ["ZCTA5CE", "period", "zori"]
    assert set(out["ZCTA5CE"]) == {"85001", "85002"}          # inner filter
    assert out.equals(
        out.sort_values(["ZCTA5CE", "period"], kind="stable", ignore_index=True)
    )
    assert len(out) == 4


def test_committed_zcta_frame_reads_committed_dataset(monkeypatch, tmp_path) -> None:
    """The panel's ZCTA universe is the committed 35-column dataset's ZCTA5CE set
    (design coverage-table semantics), zero-padded, not the geometric CBSA set."""
    import src.pipelines.panel as panel

    csv = tmp_path / "final_zcta_dataset_phoenix.csv"
    pd.DataFrame({"ZCTA5CE": [85001, 85002], "zori": [1.0, 2.0]}).to_csv(csv, index=False)
    monkeypatch.setattr(panel, "DATA_FINAL", tmp_path)

    out = panel.committed_zcta_frame("phoenix")
    assert list(out["ZCTA5CE"]) == ["85001", "85002"]


def test_committed_zcta_frame_missing_dataset_raises(monkeypatch, tmp_path) -> None:
    import src.pipelines.panel as panel

    monkeypatch.setattr(panel, "DATA_FINAL", tmp_path)
    with pytest.raises(FileNotFoundError, match="final_zcta_dataset_phoenix"):
        panel.committed_zcta_frame("phoenix")


def test_build_panel_flow_scopes_by_committed_dataset_not_geometry() -> None:
    """Structural: the flow must not resolve the metro ZCTA SET from the
    geometric CBSA-filter tasks (out-of-dataset ZIPs would enter the panel).

    Phase 2 nuance: fetch_state_zctas_task/fetch_tracts_task are allowed back
    as GEOMETRY carriers (job_accessibility_by_year needs centroids), but the
    universe must still be the committed dataset's ID set — the geometries are
    ID-filtered via committed_zcta_geometries, never CBSA-filtered.
    """
    import inspect

    from src.pipelines.panel import build_panel_flow

    src = inspect.getsource(build_panel_flow.fn)
    assert "committed_zcta_frame" in src
    assert "committed_zcta_geometries" in src
    for geo_scope_task in ("filter_zctas_task", "fetch_cbsa_boundary_task"):
        assert geo_scope_task not in src


def test_build_panel_flow_validates_all_products_before_write() -> None:
    """Structural: an invalid panel product never lands (schema check, no hatch)."""
    import inspect

    from src.pipelines.panel import build_panel_flow

    src = inspect.getsource(build_panel_flow.fn)
    for validator in (
        "validate_zori_panel",
        "validate_lodes_panel",
        "validate_acs_commute_2019",
    ):
        assert validator in src


def _square(lon: float, lat: float, size: float = 0.05) -> Polygon:
    return Polygon(
        [(lon, lat), (lon + size, lat), (lon + size, lat + size), (lon, lat + size)]
    )


def _lodes_panel_inputs(zcta_ids: list[str]):
    """Minimal offline inputs for lodes_panel_task.fn (Memphis-zone geometry)."""
    zctas = gpd.GeoDataFrame(
        {"ZCTA5CE": zcta_ids},
        geometry=[_square(-90.05 + 0.1 * i, 35.1) for i in range(len(zcta_ids))],
        crs=4326,
    )
    tracts = gpd.GeoDataFrame(
        {"GEOID": ["47157000100"]}, geometry=[_square(-90.0, 35.15)], crs=4326
    )
    state_frames = [
        pd.DataFrame(
            {
                "year": [2015, 2016],
                "zcta": ["38103", "38103"],
                "trct": ["47157000100", "47157000100"],
                "jobs": [100, 120],
            }
        )
    ]
    return state_frames, zctas, tracts, 32616


def test_lodes_panel_task_full_grid_zero_fills_absent_zctas() -> None:
    """A metro ZCTA absent from every WAC year gets job_count=0 rows (absence =
    zero jobs, matching employment_features_task); the output is exactly the
    |ZCTAs| x |years| grid, stable-sorted, with int job_count and positive
    accessibility everywhere."""
    from src.pipelines.panel import lodes_panel_task

    out = lodes_panel_task.fn(*_lodes_panel_inputs(["38103", "38104"]))

    assert list(out.columns) == ["ZCTA5CE", "year", "job_count", "job_accessibility"]
    assert len(out) == 4                                   # 2 ZCTAs x 2 years
    assert out["job_count"].dtype.kind == "i"
    grid = out.set_index(["ZCTA5CE", "year"])["job_count"]
    assert grid.loc[("38103", 2015)] == 100
    assert grid.loc[("38103", 2016)] == 120
    assert grid.loc[("38104", 2015)] == 0                  # absent from WAC -> 0
    assert grid.loc[("38104", 2016)] == 0
    assert (out["job_accessibility"] > 0).all()
    assert out.equals(
        out.sort_values(["ZCTA5CE", "year"], kind="stable", ignore_index=True)
    )


def test_lodes_panel_task_rejects_duplicated_zctas() -> None:
    """A duplicated metro ZCTA must raise loudly (memphis dup-rows regression),
    never silently multiply or collapse grid rows."""
    from src.pipelines.panel import lodes_panel_task

    with pytest.raises(pd.errors.MergeError):
        lodes_panel_task.fn(*_lodes_panel_inputs(["38103", "38103", "38104"]))


def test_acs_commute_2019_task_filters_renames_sorts() -> None:
    from src.pipelines.panel import acs_commute_2019_task

    acs_df = pd.DataFrame(
        {
            "ZCTA5CE": ["85001", "38104", "38103"],
            "commute_min_proxy": [20.0, 30.0, 24.5],
            "ttw_total": [900, 800, 1500],
        }
    )
    zctas_in_metro = pd.DataFrame({"ZCTA5CE": ["38104", "38103"]})

    out = acs_commute_2019_task.fn(acs_df, zctas_in_metro)

    assert list(out.columns) == [
        "ZCTA5CE", "commute_min_proxy_2019", "ttw_total_2019",
    ]
    assert list(out["ZCTA5CE"]) == ["38103", "38104"]      # filtered + sorted
    assert list(out["commute_min_proxy_2019"]) == [24.5, 30.0]
    assert list(out["ttw_total_2019"]) == [1500, 800]
