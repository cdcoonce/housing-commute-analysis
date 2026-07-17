"""Determinism: seeded analysis is byte-stable across repeated runs, and
pipeline aggregations are invariant to input row order."""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import polars as pl
from shapely.geometry import Polygon

import src.pipelines.lodes as lodes
from src.models.models import cv_rmse
from src.models.rq2_equity_analysis import analyze_rq2
from src.pipelines.build import aggregate_acs_to_zcta
from src.pipelines.demographics import aggregate_demographics_to_zcta


def test_cv_rmse_repeatable() -> None:
    rng = np.random.default_rng(0)
    X = rng.standard_normal((40, 3))
    y = X @ np.array([1.0, -0.5, 0.2]) + rng.standard_normal(40) * 0.1
    m1, folds1 = cv_rmse(X, y, k=3)
    m2, folds2 = cv_rmse(X, y, k=3)
    assert m1 == m2
    assert folds1 == folds2


def test_rq2_clusters_repeatable(sample_zcta_df: pl.DataFrame) -> None:
    r1 = analyze_rq2(sample_zcta_df)
    r2 = analyze_rq2(sample_zcta_df)
    if r1.cluster_labels is not None and r2.cluster_labels is not None:
        assert np.array_equal(r1.cluster_labels, r2.cluster_labels)


# ---------------------------------------------------------------------------
# Pipeline order-invariance (issue #6)
#
# Floating-point summation is order-sensitive, and the upstream services
# (Census API tract rows, TIGERweb tract features) do not guarantee stable
# row order. Each aggregation under test stable-sorts on its key (GEOID /
# trct) before reducing, so permuting input row order must yield
# BYTE-IDENTICAL output — asserted with exact float equality, never isclose.
#
# Synthetic inputs deliberately mix magnitudes (1e15 next to 1.1) so that
# reordered partial sums genuinely differ in the last ULPs if the sort is
# ever dropped: these tests fail red against unsorted aggregation.
# ---------------------------------------------------------------------------

_N_PERMUTATIONS = 5


def _adversarial_values(rng: np.random.Generator, n: int) -> np.ndarray:
    """Mixed-magnitude floats whose sequential sum depends on addend order."""
    core = np.array([1e15, 1.1, -1e15, 2.2, 0.3, 7e14, -7e14, 3.7])
    rest = rng.uniform(0.01, 1e12, n - core.size)
    return np.concatenate([core, rest])


def _square(cx: float, cy: float, half: float = 1000.0) -> Polygon:
    return Polygon([
        (cx - half, cy - half), (cx + half, cy - half),
        (cx + half, cy + half), (cx - half, cy + half),
    ])


def _tract_map(geoids: list[str]) -> pd.DataFrame:
    """Map tracts to two ZCTAs, interleaved so groups span the whole frame."""
    return pd.DataFrame({
        "GEOID": geoids,
        "ZCTA5CE": ["85001" if i % 2 == 0 else "85002" for i in range(len(geoids))],
    })


def test_acs_zcta_aggregation_order_invariant() -> None:
    """aggregate_acs_to_zcta: permuted tract rows -> byte-identical output."""
    rng = np.random.default_rng(1234)
    n = 40
    geoids = [f"04013{i:06d}" for i in range(n)]
    agg_cols = [
        "rent_to_income", "commute_min_proxy", "ttw_total",
        "pct_commute_lt10", "pct_commute_10_19", "pct_commute_20_29",
        "pct_commute_30_44", "pct_commute_45_59", "pct_commute_60_plus",
        "pct_drive_alone", "pct_carpool", "pct_transit", "pct_walk",
        "pct_wfh", "pct_car", "pct_rent_burden_30", "pct_rent_burden_50",
        "renter_share", "vehicle_access",
    ]
    acs = pd.DataFrame({
        "GEOID": geoids,
        **{col: _adversarial_values(rng, n) for col in agg_cols},
    })
    tract_map = _tract_map(geoids)

    base = aggregate_acs_to_zcta(acs, tract_map)
    for seed in range(_N_PERMUTATIONS):
        acs_shuffled = acs.sample(frac=1, random_state=seed).reset_index(drop=True)
        map_shuffled = (
            tract_map.sample(frac=1, random_state=seed + 100).reset_index(drop=True)
        )
        out = aggregate_acs_to_zcta(acs_shuffled, map_shuffled)
        pd.testing.assert_frame_equal(out, base, check_exact=True)


def test_demographics_zcta_aggregation_order_invariant() -> None:
    """aggregate_demographics_to_zcta: permuted tract rows -> byte-identical
    output (population-weighted means sum value*weight products in row order)."""
    rng = np.random.default_rng(99)
    n = 40
    geoids = [f"04013{i:06d}" for i in range(n)]
    pct_cols = ["pct_hispanic", "pct_white", "pct_black", "pct_asian", "pct_other"]
    demo = pd.DataFrame({
        "GEOID": geoids,
        "total_pop": rng.integers(1, 20000, n),
        **{col: _adversarial_values(rng, n) for col in pct_cols},
        "median_income": _adversarial_values(rng, n),
    })
    tract_map = _tract_map(geoids)

    base = aggregate_demographics_to_zcta(demo, tract_map)
    for seed in range(_N_PERMUTATIONS):
        demo_shuffled = demo.sample(frac=1, random_state=seed).reset_index(drop=True)
        map_shuffled = (
            tract_map.sample(frac=1, random_state=seed + 100).reset_index(drop=True)
        )
        out = aggregate_demographics_to_zcta(demo_shuffled, map_shuffled)
        pd.testing.assert_frame_equal(out, base, check_exact=True)


def test_job_accessibility_order_invariant() -> None:
    """job_accessibility: permuted tract features/LODES rows -> byte-identical
    output. The gravity index sums jobs_j * exp(-d_ij/decay) over tracts, so
    tract order is the reduction order. zctas_gdf order is held fixed: it only
    mirrors into output ROW order (each row's value is its own reduction) and
    is config-stable in production, unlike TIGERweb tract feature order."""
    utm = 32612
    rng = np.random.default_rng(7)
    n_tracts = 30
    trcts = [f"04013{i:06d}" for i in range(n_tracts)]
    xs = rng.uniform(300000.0, 500000.0, n_tracts)
    ys = rng.uniform(3600000.0, 3800000.0, n_tracts)
    tracts = gpd.GeoDataFrame(
        {"GEOID": trcts},
        geometry=[_square(x, y, half=500.0) for x, y in zip(xs, ys)],
        crs=utm,
    )
    jobs = np.concatenate([
        np.array([10**12, 3, 7 * 10**11, 1]),
        rng.integers(1, 10**9, n_tracts - 4),
    ])
    lodes_df = pd.DataFrame({"zcta": ["85001"] * n_tracts, "trct": trcts, "jobs": jobs})
    zctas = gpd.GeoDataFrame(
        {"ZCTA5CE": ["85001", "85002"]},
        geometry=[_square(400000.0, 3700000.0), _square(430000.0, 3720000.0)],
        crs=utm,
    )

    base = lodes.job_accessibility(zctas, tracts, lodes_df, utm)
    for seed in range(_N_PERMUTATIONS):
        tracts_shuffled = (
            tracts.sample(frac=1, random_state=seed).reset_index(drop=True)
        )
        lodes_shuffled = (
            lodes_df.sample(frac=1, random_state=seed + 100).reset_index(drop=True)
        )
        out = lodes.job_accessibility(zctas, tracts_shuffled, lodes_shuffled, utm)
        pd.testing.assert_frame_equal(out, base, check_exact=True)
