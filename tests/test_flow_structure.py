"""Structural tests for the Prefect pipeline flow (no network)."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import geopandas as gpd
import pandas as pd
import pytest
from prefect import Flow
from prefect.cache_policies import TASK_SOURCE
from shapely.geometry import Polygon

from src.pipelines.build import build_final_dataset, build_metro_flow


def test_build_metro_flow_is_a_flow() -> None:
    assert isinstance(build_metro_flow, Flow)


def test_build_final_dataset_delegates_to_flow() -> None:
    # alias preserves the public name run_pipeline.py imports
    assert build_final_dataset.__name__ == "build_final_dataset"
    assert callable(build_final_dataset)


def _cache_key(task, inputs: dict) -> str:
    """Compute a task's persisted cache key for the given inputs.

    TASK_SOURCE.compute_key reads only ``task_ctx.task`` and INPUTS ignores
    task_ctx, so a ``SimpleNamespace(task=...)`` is a sufficient context — no
    server/client/result-store plumbing required.
    """
    ctx = SimpleNamespace(task=task)
    return task.cache_policy.compute_key(task_ctx=ctx, inputs=inputs, flow_parameters={})


def test_counties_tasks_have_distinct_cache_keys() -> None:
    """Regression guard for the INPUTS-only cache-key collision (Critical bug).

    fetch_tracts_task, fetch_acs_task, and fetch_demographics_task all take the
    same sole ``counties`` argument. Under bare INPUTS their cache keys collide on
    ONE key (values only), so with persist_result=True the first task to run
    poisons a shared store and the others read back its result. Adding TASK_SOURCE
    to the policy makes the keys task-body-distinct. Prove that here: identical
    inputs, keys MUST differ.
    """
    from src.pipelines.build import (
        fetch_acs_task,
        fetch_demographics_task,
        fetch_tracts_task,
    )

    inputs = {"counties": [("04", "013"), ("04", "021")]}  # identical to all three
    keys = {
        "tracts": _cache_key(fetch_tracts_task, inputs),
        "acs": _cache_key(fetch_acs_task, inputs),
        "demographics": _cache_key(fetch_demographics_task, inputs),
    }
    assert len(set(keys.values())) == 3, f"cache keys collide: {keys}"


def test_cacheable_tasks_include_task_source_component() -> None:
    """Structural backstop: every counties/URL-keyed cacheable task's policy must
    include a TASK_SOURCE component, so identical input VALUES cannot collide
    across different task bodies (this is what makes the keys above distinct).
    """
    from src.pipelines.build import (
        fetch_acs_task,
        fetch_demographics_task,
        fetch_lodes_task,
        fetch_tracts_task,
    )
    from src.pipelines.panel import fetch_zori_series_task

    task_source_type = type(TASK_SOURCE)
    for task in (
        fetch_tracts_task,
        fetch_acs_task,
        fetch_demographics_task,
        fetch_lodes_task,
        fetch_zori_series_task,
    ):
        policies = getattr(task.cache_policy, "policies", [task.cache_policy])
        assert any(isinstance(p, task_source_type) for p in policies), (
            f"{task.name} cache_policy lacks a TASK_SOURCE component: {task.cache_policy}"
        )


def test_zori_tasks_have_distinct_cache_keys() -> None:
    """fetch_zori_series_task must never share a persisted result with
    fetch_zori_task: both are URL-keyed, so with a TASK_SOURCE-free policy the
    same url value could collide across the two task bodies. Inputs differ too
    (zip_prefixes), but the TASK_SOURCE component is the structural guarantee.
    """
    from src.pipelines.build import fetch_zori_task
    from src.pipelines.panel import fetch_zori_series_task

    key_series = _cache_key(
        fetch_zori_series_task, {"url": "x", "zip_prefixes": ("850",)}
    )
    key_latest = _cache_key(fetch_zori_task, {"url": "x"})
    assert key_series != key_latest


def test_build_panel_flow_is_a_flow() -> None:
    from src.pipelines.panel import build_panel_flow

    assert isinstance(build_panel_flow, Flow)


def test_employment_tasks_exist() -> None:
    from prefect import Task

    from src.pipelines.build import employment_features_task, fetch_lodes_task

    assert isinstance(fetch_lodes_task, Task)
    assert isinstance(employment_features_task, Task)


def _square(lon: float, lat: float, size: float = 0.05) -> Polygon:
    return Polygon(
        [(lon, lat), (lon + size, lat), (lon + size, lat + size), (lon, lat + size)]
    )


def _employment_inputs(zcta_ids: list[str]):
    """Minimal offline inputs for employment_features_task.fn."""
    zctas = gpd.GeoDataFrame(
        {"ZCTA5CE": zcta_ids},
        geometry=[_square(-90.05 + 0.1 * i, 35.1) for i in range(len(zcta_ids))],
        crs=4326,
    )
    tracts = gpd.GeoDataFrame(
        {"GEOID": ["47157000100"]}, geometry=[_square(-90.0, 35.15)], crs=4326
    )
    lodes = pd.DataFrame(
        {"zcta": ["38103"], "trct": ["47157000100"], "jobs": [100]}
    )
    return lodes, zctas, tracts, [(35.15, -90.05)], 32616


def test_employment_features_task_rejects_duplicated_zctas() -> None:
    """Regression guard for silent row multiplication (memphis duplicate-rows bug).

    A duplicated ZCTA in zctas_in_metro (e.g. from overlapping zip prefixes)
    duplicates the distance base frame; the merges must raise MergeError loudly
    instead of silently multiplying rows.
    """
    from src.pipelines.build import employment_features_task

    with pytest.raises(pd.errors.MergeError):
        employment_features_task.fn(*_employment_inputs(["38103", "38103", "38104"]))


def test_employment_features_task_unique_zctas_pass() -> None:
    """Happy path: unique ZCTAs produce one row each, job_count filled to 0."""
    from src.pipelines.build import employment_features_task

    out = employment_features_task.fn(*_employment_inputs(["38103", "38104"]))
    assert sorted(out["ZCTA5CE"]) == ["38103", "38104"]
    assert len(out) == 2
    assert out["job_count"].notna().all()


def test_final_merge_chain_validates_cardinality() -> None:
    """Structural backstop: every ZCTA5CE-keyed merge in the Step-7 final merge
    chain must declare validate="one_to_one" — the left base (zcta_aggregated)
    is groupby-unique and every right frame is one-row-per-ZCTA, so any key
    duplication is a bug that must raise MergeError, not multiply rows.
    """
    src = inspect.getsource(build_metro_flow.fn)
    n_zcta_merges = src.count('on="ZCTA5CE"')
    # demographics, zori, transit_density, area, employment
    assert n_zcta_merges >= 5, f"expected >=5 ZCTA5CE merges, found {n_zcta_merges}"
    n_validated = src.count('validate="one_to_one"')
    assert n_validated >= n_zcta_merges, (
        f"only {n_validated} of {n_zcta_merges} ZCTA5CE merges in build_metro_flow "
        'declare validate="one_to_one"'
    )
