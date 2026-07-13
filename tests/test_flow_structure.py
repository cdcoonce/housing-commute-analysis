"""Structural tests for the Prefect pipeline flow (no network)."""
from __future__ import annotations

from types import SimpleNamespace

from prefect import Flow
from prefect.cache_policies import TASK_SOURCE

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

    task_source_type = type(TASK_SOURCE)
    for task in (fetch_tracts_task, fetch_acs_task, fetch_demographics_task, fetch_lodes_task):
        policies = getattr(task.cache_policy, "policies", [task.cache_policy])
        assert any(isinstance(p, task_source_type) for p in policies), (
            f"{task.name} cache_policy lacks a TASK_SOURCE component: {task.cache_policy}"
        )


def test_employment_tasks_exist() -> None:
    from prefect import Task

    from src.pipelines.build import employment_features_task, fetch_lodes_task

    assert isinstance(fetch_lodes_task, Task)
    assert isinstance(employment_features_task, Task)
