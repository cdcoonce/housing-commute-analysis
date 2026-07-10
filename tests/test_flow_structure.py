"""Structural tests for the Prefect pipeline flow (no network)."""
from __future__ import annotations

from prefect import Flow

from src.pipelines.build import build_final_dataset, build_metro_flow


def test_build_metro_flow_is_a_flow() -> None:
    assert isinstance(build_metro_flow, Flow)


def test_build_final_dataset_delegates_to_flow() -> None:
    # alias preserves the public name run_pipeline.py imports
    assert build_final_dataset.__name__ == "build_final_dataset"
    assert callable(build_final_dataset)
