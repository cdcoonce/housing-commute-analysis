# Employment-Center Variables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three LODES-derived employment variables (`job_density`, `distance_to_cbd_km`, `job_accessibility`) to the pipeline and analysis, per `docs/plans/2026-07-10-employment-center-variables-design.md`.

**Architecture:** New `src/pipelines/lodes.py` module (fetch LEHD LODES8 WAC + crosswalk per state, aggregate to ZCTA/tract, compute distance and gravity features) wired into `build_metro_flow` as one cacheable fetch task + one CPU compute task. Schema goes 32 → 35 columns, forcing a full 9-metro rebuild held to a byte-identity gate on all non-live columns. Analysis integration is append-only at RQ1/RQ2/RQ3 entry points.

**Tech Stack:** Python 3.11+, pandas/geopandas/polars, Prefect 3 (local-only), pytest, uv.

## Global Constraints

- Run all tests with `uv run pytest` from the repo root. Lint with `uv run ruff check src/ tests/`.
- Commit messages: conventional style (`feat:`, `fix:`, `test:`, `docs:`, `chore:`). **No Co-Authored-By or agent-attribution lines.**
- All ZCTA join keys are `str` zero-padded to 5 digits (`.astype(str).str.zfill(5)`) — every existing merge does this.
- Prefect cacheable tasks use `**NETWORK_RETRIES, **_CACHE` where `_CACHE = {"cache_policy": INPUTS + TASK_SOURCE, "cache_expiration": CACHE_TTL, "persist_result": True}` (see `src/pipelines/build.py:45-49`). Inputs to cacheable tasks must be hashable (tuples/str/int — never DataFrames).
- Do NOT add `pyarrow` as a dependency. Do NOT set `result_storage` on tasks (unsaved-block TypeError; documented in `build.py:34-36`).
- New constants: `LODES_YEAR = 2021`, `GRAVITY_DECAY_KM = 10.0` — defined once in `src/pipelines/lodes.py`, imported everywhere else.
- The live rebuild (Phase 2) needs `CENSUS_API_KEY` in `.env` and network access. Everything else runs offline.
- Between Task 7 and Task 9, `tests/test_schema.py::test_all_committed_datasets_pass_schema` is EXPECTED red locally (committed CSVs lack the new columns until the rebuild). Do not push or open a PR in that window; Phase 1+2 land as one PR.

## File Structure

```
Create:
  src/pipelines/lodes.py          # LODES fetch + aggregation + distance + gravity (one responsibility: employment features)
  tests/test_lodes.py             # unit tests for everything in lodes.py (offline, monkeypatched HTTP)
  scripts/rebuild_gate.py         # Phase 2 baseline-equivalence + sanity gate (kept for future rebuilds)
Modify:
  src/pipelines/utils.py          # http_csv_to_df: pass-through read_csv kwargs (gzip support)
  src/pipelines/config.py         # cbd_points per metro
  src/pipelines/build.py          # 2 new tasks, flow wiring, column_order 32→35
  src/pipelines/schema.py         # REQUIRED_COLUMNS + _NON_NEGATIVE_COLUMNS + docstring
  src/pipelines/manifest.py       # _SOURCE_URLS["lodes"] + lodes_year field
  tests/test_utils.py             # gzip pass-through test (create if absent)
  tests/test_config.py            # cbd_points validation
  tests/test_flow_structure.py    # fetch_lodes_task in TASK_SOURCE structural test
  tests/test_manifest.py          # lodes provenance assertions
  tests/conftest.py               # 3 new fixture columns
  src/models/rq1_housing_commute_tradeoff.py   # required_cols + matrices + model_df (append-only)
  src/models/rq2_equity_analysis.py            # controls list + job_accessibility ANOVA + anova_names
  src/models/rq3_aci_analysis.py               # feature_candidates list
  tests/test_rq1.py, tests/test_rq2.py, tests/test_rq3.py   # new-variable assertions
  data/final/*.csv, data/final/*.manifest.json # regenerated (Phase 2)
  README.md, RUNNING_PIPELINE.md, src/pipelines/PIPELINE_README.md, docs/findings.md  # Phase 4
```

---

# Phase 1 — LODES module, config, pipeline wiring, contract

### Task 1: gzip-capable `http_csv_to_df`

**Files:**
- Modify: `src/pipelines/utils.py:45-86`
- Test: `tests/test_utils.py` (create if it does not exist; if it exists, append)

**Interfaces:**
- Produces: `http_csv_to_df(url: str, timeout: int = 180, **read_csv_kwargs) -> pd.DataFrame` — existing callers (`zori.py`) pass no kwargs and are unaffected. Task 3 calls it with `compression="gzip"`, `dtype=...`, `usecols=...`.

- [ ] **Step 1: Write the failing test**

In `tests/test_utils.py` (create with this content if absent; otherwise append the imports it lacks and the two tests):

```python
"""Tests for HTTP/CSV utilities."""
from __future__ import annotations

import gzip
import io

import pandas as pd

import src.pipelines.utils as utils


class _StubResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        pass


class _StubSession:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def get(self, url: str, timeout: int = 180, params=None):
        return _StubResponse(self._content)


def test_http_csv_to_df_plain_csv_unchanged(monkeypatch) -> None:
    csv_bytes = b"a,b\n1,2\n"
    monkeypatch.setattr(utils, "_get_session", lambda: _StubSession(csv_bytes))
    df = utils.http_csv_to_df("https://example.com/x.csv")
    assert df.shape == (1, 2) and df["a"][0] == 1


def test_http_csv_to_df_gzip_passthrough(monkeypatch) -> None:
    """LODES files are gzip-as-payload: requests does NOT auto-decode them and
    pandas cannot infer compression from BytesIO — the kwarg must reach read_csv."""
    raw = b"w_geocode,C000\n040130001001000,42\n"
    gz = gzip.compress(raw)
    monkeypatch.setattr(utils, "_get_session", lambda: _StubSession(gz))
    df = utils.http_csv_to_df(
        "https://example.com/x.csv.gz",
        compression="gzip",
        dtype={"w_geocode": str},
    )
    assert df["w_geocode"][0] == "040130001001000"  # str dtype preserved leading zero
    assert df["C000"][0] == 42
```

- [ ] **Step 2: Run tests to verify the gzip one fails**

Run: `uv run pytest tests/test_utils.py -v`
Expected: `test_http_csv_to_df_gzip_passthrough` FAILS (`TypeError: http_csv_to_df() got an unexpected keyword argument 'compression'`); the plain test PASSES.

- [ ] **Step 3: Implement the pass-through**

In `src/pipelines/utils.py`, change the signature and the `read_csv` call (docstring gains one param note):

```python
def http_csv_to_df(url: str, timeout: int = 180, **read_csv_kwargs) -> pd.DataFrame:
```

and inside the `try`:

```python
        return pd.read_csv(io.BytesIO(response.content), **read_csv_kwargs)
```

Add to the docstring's Parameters section:

```
    **read_csv_kwargs
        Passed through to pandas.read_csv — e.g. compression="gzip" for
        gzip-as-payload files (requests only auto-decodes transfer-encoding
        gzip, and pandas cannot infer compression from a BytesIO buffer),
        dtype={...} to preserve leading zeros, usecols=[...] to bound memory.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_utils.py -v`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/utils.py tests/test_utils.py
git commit -m "feat(pipeline): pass read_csv kwargs through http_csv_to_df for gzip sources"
```

---

### Task 2: `lodes.py` — constants, URL builders, state derivation

**Files:**
- Create: `src/pipelines/lodes.py`
- Test: `tests/test_lodes.py` (create)

**Interfaces:**
- Produces: `LODES_YEAR: int = 2021`, `GRAVITY_DECAY_KM: float = 10.0`, `wac_url(state_postal, year) -> str`, `xwalk_url(state_postal) -> str`, `states_for_counties(counties) -> tuple[str, ...]` (sorted postal codes; raises `KeyError` on unmapped FIPS). Tasks 3–5 add functions to this module; Task 7 imports from it.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lodes.py`:

```python
"""Unit tests for src/pipelines/lodes.py (all offline)."""
from __future__ import annotations

import math

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon

import src.pipelines.lodes as lodes


def test_wac_url_pattern() -> None:
    assert lodes.wac_url("az", 2021) == (
        "https://lehd.ces.census.gov/data/lodes/LODES8/az/wac/az_wac_S000_JT00_2021.csv.gz"
    )


def test_xwalk_url_pattern() -> None:
    assert lodes.xwalk_url("tn") == (
        "https://lehd.ces.census.gov/data/lodes/LODES8/tn/tn_xwalk.csv.gz"
    )


def test_states_for_counties_memphis_tristate() -> None:
    """Memphis spans TN+MS+AR — all three states must be fetched or suburbs are lost."""
    counties = [("47", "157"), ("47", "047"), ("05", "035"), ("28", "033")]
    assert lodes.states_for_counties(counties) == ("ar", "ms", "tn")


def test_states_for_counties_unmapped_fips_raises() -> None:
    with pytest.raises(KeyError):
        lodes.states_for_counties([("99", "001")])
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_lodes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.pipelines.lodes'` (collection error).

- [ ] **Step 3: Create the module**

Create `src/pipelines/lodes.py`:

```python
"""LEHD LODES employment data: fetch, ZCTA/tract aggregation, derived features.

Source: LODES8 Workplace Area Characteristics (WAC) — job counts by 2020 census
block. 2020 blocks nest exactly in the 2020-vintage ZCTAs this pipeline uses,
so block→ZCTA assignment via the LODES crosswalk is exact containment (no
areal interpolation). Public domain, no auth. LODES counts UI-covered + federal
civilian jobs only (no self-employed / military / informal).

Block-level values are noise-infused for confidentiality — only ZCTA- and
tract-level sums are consumed here, where the noise washes out.
"""
from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from .utils import http_csv_to_df

logger = logging.getLogger(__name__)

# 2021 pairs with the ACS 5-Year 2017-2021 commute vintage (acs.DEFAULT_ACS_YEAR).
# LODES year = April 1 snapshot; 2021 is COVID-affected (documented in the design).
LODES_YEAR = 2021
LODES_VERSION = "LODES8"  # 2020 census blocks — do NOT use LODES7 (2010 blocks)
LODES_BASE_URL = "https://lehd.ces.census.gov/data/lodes"

# Exponential decay length (km) for the gravity job-accessibility index.
# The single sensitivity knob for job_accessibility; see design doc.
GRAVITY_DECAY_KM = 10.0

# Only the states covering the 9 configured metros. Extend when adding metros.
STATE_FIPS_TO_POSTAL = {
    "04": "az", "05": "ar", "06": "ca", "08": "co", "12": "fl", "13": "ga",
    "17": "il", "28": "ms", "47": "tn", "48": "tx", "53": "wa",
}


def wac_url(state_postal: str, year: int = LODES_YEAR) -> str:
    """WAC file URL: all-jobs (JT00), all-workers segment (S000), one state-year."""
    return (
        f"{LODES_BASE_URL}/{LODES_VERSION}/{state_postal}/wac/"
        f"{state_postal}_wac_S000_JT00_{year}.csv.gz"
    )


def xwalk_url(state_postal: str) -> str:
    """Geography crosswalk URL: maps 2020 blocks to ZCTA, tract, and more."""
    return f"{LODES_BASE_URL}/{LODES_VERSION}/{state_postal}/{state_postal}_xwalk.csv.gz"


def states_for_counties(counties: list[tuple[str, str]]) -> tuple[str, ...]:
    """Distinct postal codes for a metro's (state_fips, county_fips) list, sorted.

    Returns a tuple (hashable) so it can key a cacheable Prefect task.

    Raises
    ------
    KeyError
        If a state FIPS has no postal mapping (extend STATE_FIPS_TO_POSTAL).
    """
    fips = sorted({state for state, _ in counties})
    unmapped = [f for f in fips if f not in STATE_FIPS_TO_POSTAL]
    if unmapped:
        raise KeyError(
            f"No postal mapping for state FIPS {unmapped}; extend STATE_FIPS_TO_POSTAL"
        )
    return tuple(sorted(STATE_FIPS_TO_POSTAL[f] for f in fips))
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_lodes.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/lodes.py tests/test_lodes.py
git commit -m "feat(pipeline): LODES module scaffold — URLs, vintage constants, state derivation"
```

---

### Task 3: `lodes.py` — fetch + block→(zcta, tract) aggregation

**Files:**
- Modify: `src/pipelines/lodes.py`
- Test: `tests/test_lodes.py`

**Interfaces:**
- Consumes: `http_csv_to_df(url, **read_csv_kwargs)` from Task 1.
- Produces: `fetch_state_jobs(state_postal, year) -> pd.DataFrame` and `fetch_metro_lodes(states: tuple[str, ...], year: int) -> pd.DataFrame`, both returning the slim frame `[zcta: str5, trct: str11, jobs: int]`. Task 7's `fetch_lodes_task` wraps `fetch_metro_lodes`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lodes.py`:

```python
def _fake_http(monkeypatch, wac: pd.DataFrame, xwalk: pd.DataFrame) -> None:
    """Route lodes' http_csv_to_df by URL to synthetic WAC / crosswalk frames."""
    def fake(url: str, timeout: int = 180, **kwargs):
        return wac.copy() if "/wac/" in url else xwalk.copy()
    monkeypatch.setattr(lodes, "http_csv_to_df", fake)


def test_fetch_state_jobs_aggregates_and_drops_unassigned(monkeypatch) -> None:
    wac = pd.DataFrame({
        "w_geocode": ["040130001001000", "040130001001001", "040130002002000",
                      "040130003003000", "040130004004000"],
        "C000": [10, 5, 7, 3, 9],
    })
    xwalk = pd.DataFrame({
        "tabblk2020": ["040130001001000", "040130001001001", "040130002002000",
                       "040130003003000", "040130004004000"],
        "zcta": ["85001", "85001", "85002", "", "99999"],  # blank + sentinel dropped
        "trct": ["04013000100", "04013000100", "04013000200",
                 "04013000300", "04013000400"],
    })
    _fake_http(monkeypatch, wac, xwalk)
    out = lodes.fetch_state_jobs("az", 2021)
    assert list(out.columns) == ["zcta", "trct", "jobs"]
    # blocks 1+2 aggregate into one (zcta, trct) pair
    row = out[(out["zcta"] == "85001") & (out["trct"] == "04013000100")]
    assert row["jobs"].item() == 15
    # blank-zcta and 99999-sentinel blocks are dropped entirely
    assert set(out["zcta"]) == {"85001", "85002"}


def test_fetch_metro_lodes_concats_states(monkeypatch) -> None:
    wac = pd.DataFrame({"w_geocode": ["1" * 15], "C000": [4]})
    xwalk = pd.DataFrame({
        "tabblk2020": ["1" * 15], "zcta": ["38103"], "trct": ["1" * 11],
    })
    _fake_http(monkeypatch, wac, xwalk)
    out = lodes.fetch_metro_lodes(("ar", "ms", "tn"), 2021)
    # one identical synthetic row per state, aggregated across the concat
    assert out["jobs"].sum() == 12
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_lodes.py -v`
Expected: the two new tests FAIL with `AttributeError: module 'src.pipelines.lodes' has no attribute 'fetch_state_jobs'`.

- [ ] **Step 3: Implement**

Append to `src/pipelines/lodes.py`:

```python
def fetch_state_jobs(state_postal: str, year: int = LODES_YEAR) -> pd.DataFrame:
    """One state's block-level jobs joined to ZCTA + tract via the LODES crosswalk.

    Returns the slim frame [zcta, trct, jobs] aggregated to (zcta, trct) pairs.
    Raw block rows and the (large, ~10-60 MB gz) crosswalk are NOT retained —
    this keeps the Prefect-persisted cache result small.

    Blocks with a blank or "99999" crosswalk zcta (unpopulated water/park
    blocks) are dropped; they carry ~0 jobs.
    """
    wac = http_csv_to_df(
        wac_url(state_postal, year),
        compression="gzip",
        dtype={"w_geocode": str},
        usecols=["w_geocode", "C000"],
    )
    xwalk = http_csv_to_df(
        xwalk_url(state_postal),
        compression="gzip",
        dtype={"tabblk2020": str, "zcta": str, "trct": str},
        usecols=["tabblk2020", "zcta", "trct"],
    )
    xwalk = xwalk[xwalk["zcta"].str.fullmatch(r"\d{5}", na=False)]
    xwalk = xwalk[xwalk["zcta"] != "99999"]

    merged = wac.merge(xwalk, left_on="w_geocode", right_on="tabblk2020", how="inner")
    out = (
        merged.groupby(["zcta", "trct"], as_index=False)["C000"]
        .sum()
        .rename(columns={"C000": "jobs"})
    )
    logger.info(
        "LODES %s %s: %d (zcta, tract) pairs, %d jobs",
        state_postal, year, len(out), int(out["jobs"].sum()),
    )
    return out


def fetch_metro_lodes(states: tuple[str, ...], year: int = LODES_YEAR) -> pd.DataFrame:
    """All states' job frames for a metro, concatenated and re-aggregated.

    A (zcta, tract) pair belongs to exactly one state, so the re-aggregation is
    defensive only. `states` is a tuple so the wrapping Prefect task stays
    cacheable on its inputs.
    """
    frames = [fetch_state_jobs(s, year) for s in states]
    return (
        pd.concat(frames, ignore_index=True)
        .groupby(["zcta", "trct"], as_index=False)["jobs"]
        .sum()
    )
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_lodes.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/lodes.py tests/test_lodes.py
git commit -m "feat(pipeline): fetch LODES WAC + crosswalk, aggregate blocks to (zcta, tract) jobs"
```

---

### Task 4: `lodes.py` — ZCTA job counts + distance-to-CBD

**Files:**
- Modify: `src/pipelines/lodes.py`
- Test: `tests/test_lodes.py`

**Interfaces:**
- Produces: `zcta_job_counts(lodes_df) -> pd.DataFrame [ZCTA5CE, job_count]`; `distance_to_cbd_km(zctas_gdf, cbd_points: list[tuple[float, float]], utm_zone: int) -> pd.DataFrame [ZCTA5CE, distance_to_cbd_km]`. `cbd_points` are **(lat, lon)** tuples — converted internally to shapely `(x=lon, y=lat)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lodes.py`:

```python
def test_zcta_job_counts_sums_tracts_and_zfills() -> None:
    lodes_df = pd.DataFrame({
        "zcta": ["85001", "85001", "8500"],  # "8500" exercises zfill
        "trct": ["04013000100", "04013000200", "04013000300"],
        "jobs": [15, 7, 3],
    })
    out = lodes.zcta_job_counts(lodes_df)
    assert list(out.columns) == ["ZCTA5CE", "job_count"]
    assert out.set_index("ZCTA5CE").loc["85001", "job_count"] == 22
    assert out.set_index("ZCTA5CE").loc["08500", "job_count"] == 3


def _square(cx: float, cy: float, half: float = 1000.0) -> Polygon:
    return Polygon([
        (cx - half, cy - half), (cx + half, cy - half),
        (cx + half, cy + half), (cx - half, cy + half),
    ])


def test_distance_to_cbd_km_zero_at_centroid_and_min_over_points() -> None:
    """Two 2km squares in UTM 12N, centroids 10km apart. A CBD point placed at
    each centroid (via inverse projection to lat/lon) must give ~0 km for both
    ZCTAs — proving both the centroid math and the min-over-points rule."""
    import pyproj

    utm = 32612
    c0, c1 = (400000.0, 3700000.0), (410000.0, 3700000.0)
    zctas = gpd.GeoDataFrame(
        {"ZCTA5CE": ["85001", "85002"]},
        geometry=[_square(*c0), _square(*c1)],
        crs=utm,
    )
    to_wgs = pyproj.Transformer.from_crs(utm, 4326, always_xy=True)
    lon0, lat0 = to_wgs.transform(*c0)
    lon1, lat1 = to_wgs.transform(*c1)

    # Single CBD at centroid 0: ZCTA 0 is ~0 km away, ZCTA 1 is ~10 km away
    single = lodes.distance_to_cbd_km(zctas, [(lat0, lon0)], utm)
    d = single.set_index("ZCTA5CE")["distance_to_cbd_km"]
    assert d["85001"] < 0.01
    assert abs(d["85002"] - 10.0) < 0.1

    # Dual CBD (DFW pattern): min over points → both ~0
    dual = lodes.distance_to_cbd_km(zctas, [(lat0, lon0), (lat1, lon1)], utm)
    d2 = dual.set_index("ZCTA5CE")["distance_to_cbd_km"]
    assert d2["85001"] < 0.01 and d2["85002"] < 0.01
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_lodes.py -v`
Expected: the two new tests FAIL with `AttributeError` (functions not defined).

- [ ] **Step 3: Implement**

Append to `src/pipelines/lodes.py`:

```python
def zcta_job_counts(lodes_df: pd.DataFrame) -> pd.DataFrame:
    """Total jobs per ZCTA: [ZCTA5CE (str5), job_count]."""
    out = lodes_df.groupby("zcta", as_index=False)["jobs"].sum()
    out["ZCTA5CE"] = out["zcta"].astype(str).str.zfill(5)
    return out[["ZCTA5CE", "jobs"]].rename(columns={"jobs": "job_count"})


def distance_to_cbd_km(
    zctas_gdf: gpd.GeoDataFrame,
    cbd_points: list[tuple[float, float]],
    utm_zone: int,
) -> pd.DataFrame:
    """Euclidean km from each ZCTA centroid to the nearest CBD point.

    cbd_points are (lat, lon) tuples (human/map order); min over points supports
    dual-CBD metros (DFW). Distances computed in the metro's UTM CRS.
    """
    zctas = zctas_gdf.to_crs(utm_zone)
    centroids = zctas.geometry.centroid
    cbd_series = gpd.GeoSeries(
        [Point(lon, lat) for lat, lon in cbd_points], crs=4326
    ).to_crs(utm_zone)
    per_point = np.stack(
        [centroids.distance(pt).to_numpy() for pt in cbd_series], axis=1
    )
    return pd.DataFrame({
        "ZCTA5CE": zctas["ZCTA5CE"].astype(str).str.zfill(5),
        "distance_to_cbd_km": per_point.min(axis=1) / 1000.0,
    })
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_lodes.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/lodes.py tests/test_lodes.py
git commit -m "feat(pipeline): ZCTA job counts + min-over-points distance to CBD"
```

---

### Task 5: `lodes.py` — gravity job-accessibility index

**Files:**
- Modify: `src/pipelines/lodes.py`
- Test: `tests/test_lodes.py`

**Interfaces:**
- Consumes: the `[zcta, trct, jobs]` frame from Task 3; tract geometries carry a `GEOID` column (11-digit, as fetched by `tiger.get_tracts_for_counties`).
- Produces: `job_accessibility(zctas_gdf, tracts_gdf, lodes_df, utm_zone, decay_km=GRAVITY_DECAY_KM) -> pd.DataFrame [ZCTA5CE, job_accessibility]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lodes.py`:

```python
def test_job_accessibility_hand_computable_two_tracts() -> None:
    """One ZCTA co-centered with tract A; tract B exactly 10 km away.
    A_i = jobs_A * exp(0) + jobs_B * exp(-10/10) = 100 + 50*e^-1."""
    utm = 32612
    zctas = gpd.GeoDataFrame(
        {"ZCTA5CE": ["85001"]},
        geometry=[_square(400000.0, 3700000.0)],
        crs=utm,
    )
    tracts = gpd.GeoDataFrame(
        {"GEOID": ["04013000100", "04013000200"]},
        geometry=[_square(400000.0, 3700000.0, half=500.0),
                  _square(410000.0, 3700000.0, half=500.0)],
        crs=utm,
    )
    lodes_df = pd.DataFrame({
        "zcta": ["85001", "85001"],
        "trct": ["04013000100", "04013000200"],
        "jobs": [100, 50],
    })
    out = lodes.job_accessibility(zctas, tracts, lodes_df, utm, decay_km=10.0)
    expected = 100.0 + 50.0 * math.exp(-1.0)
    assert np.isclose(out["job_accessibility"].item(), expected, rtol=1e-6)


def test_job_accessibility_no_matching_tracts_returns_zero() -> None:
    utm = 32612
    zctas = gpd.GeoDataFrame(
        {"ZCTA5CE": ["85001"]}, geometry=[_square(400000.0, 3700000.0)], crs=utm
    )
    tracts = gpd.GeoDataFrame(
        {"GEOID": ["04013000900"]},
        geometry=[_square(410000.0, 3700000.0, half=500.0)],
        crs=utm,
    )
    lodes_df = pd.DataFrame({"zcta": ["85001"], "trct": ["04013000100"], "jobs": [7]})
    out = lodes.job_accessibility(zctas, tracts, lodes_df, utm)
    assert out["job_accessibility"].item() == 0.0
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_lodes.py -v`
Expected: both new tests FAIL with `AttributeError`.

- [ ] **Step 3: Implement**

Append to `src/pipelines/lodes.py`:

```python
def job_accessibility(
    zctas_gdf: gpd.GeoDataFrame,
    tracts_gdf: gpd.GeoDataFrame,
    lodes_df: pd.DataFrame,
    utm_zone: int,
    decay_km: float = GRAVITY_DECAY_KM,
) -> pd.DataFrame:
    """Hansen-type gravity index: A_i = sum_j jobs_j * exp(-d_ij / decay_km).

    j ranges over the metro's census tracts (jobs summed from the LODES frame);
    d_ij is UTM Euclidean distance between ZCTA centroid i and tract centroid j.
    Tract altitude keeps the distance matrix small and further averages LODES
    block noise. Jobs outside the metro's counties are not counted (documented
    limitation for edge ZCTAs — consistent with the ACS county frame).
    """
    tract_jobs = lodes_df.groupby("trct", as_index=False)["jobs"].sum()
    tracts = tracts_gdf.to_crs(utm_zone).copy()
    tracts["trct"] = tracts["GEOID"].astype(str).str.zfill(11)
    tracts = tracts.merge(tract_jobs, on="trct", how="inner")

    zctas = zctas_gdf.to_crs(utm_zone)
    zcta_ids = zctas["ZCTA5CE"].astype(str).str.zfill(5)

    if tracts.empty:
        logger.warning("job_accessibility: no tracts matched LODES jobs; returning 0s")
        return pd.DataFrame({
            "ZCTA5CE": zcta_ids,
            "job_accessibility": np.zeros(len(zctas)),
        })

    tract_cent = tracts.geometry.centroid
    tract_xy = np.column_stack([tract_cent.x.to_numpy(), tract_cent.y.to_numpy()])
    jobs = tracts["jobs"].to_numpy(dtype=float)

    zcta_cent = zctas.geometry.centroid
    zcta_xy = np.column_stack([zcta_cent.x.to_numpy(), zcta_cent.y.to_numpy()])

    # Pairwise (n_zcta, n_tract) distances in km
    d_km = np.sqrt(
        ((zcta_xy[:, None, :] - tract_xy[None, :, :]) ** 2).sum(axis=2)
    ) / 1000.0
    access = (jobs[None, :] * np.exp(-d_km / decay_km)).sum(axis=1)

    return pd.DataFrame({"ZCTA5CE": zcta_ids, "job_accessibility": access})
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_lodes.py -v`
Expected: 10 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/lodes.py tests/test_lodes.py
git commit -m "feat(pipeline): gravity job-accessibility index over metro tracts"
```

---

### Task 6: CBD points in `METRO_CONFIGS`

**Files:**
- Modify: `src/pipelines/config.py:25-136`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `METRO_CONFIGS[metro]["cbd_points"]: list[tuple[float, float]]` — (lat, lon) tuples consumed by `distance_to_cbd_km` via Task 7's flow wiring.

- [ ] **Step 1: Write the failing tests**

In `tests/test_config.py`, change the constant and add two tests:

```python
REQUIRED_KEYS = {"cbsa_code", "counties", "zip_prefixes", "utm_zone", "name", "cbd_points"}
```

```python
def test_all_metros_have_plausible_cbd_points() -> None:
    """Every metro needs >=1 (lat, lon) CBD point inside the continental US."""
    for metro, cfg in METRO_CONFIGS.items():
        points = cfg["cbd_points"]
        assert isinstance(points, list) and len(points) >= 1, (
            f"Metro '{metro}' has no cbd_points"
        )
        for lat, lon in points:
            assert 24.0 < lat < 49.0, f"Metro '{metro}' CBD lat out of CONUS range: {lat}"
            assert -125.0 < lon < -66.0, f"Metro '{metro}' CBD lon out of CONUS range: {lon}"


def test_dallas_is_dual_cbd() -> None:
    """DFW is functionally dual-CBD: Dallas and Fort Worth, ~50 km apart."""
    assert len(METRO_CONFIGS["dallas"]["cbd_points"]) == 2
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: `test_all_metros_have_required_keys`, `test_all_metros_have_plausible_cbd_points`, `test_dallas_is_dual_cbd` FAIL with `KeyError: 'cbd_points'` / missing-keys assertion.

- [ ] **Step 3: Add the coordinates**

In `src/pipelines/config.py`, first extend the format comment block (line ~24) with one line:

```python
#   "cbd_points": List of (lat, lon) CBD reference points (downtown core /
#                 city hall, per Holian & Kahn CES-WP-11-21 CBD anchoring;
#                 DFW is dual-CBD). Used for distance_to_cbd_km.
```

Then add a `"cbd_points"` entry to each metro dict (after `"utm_zone"`):

```python
    # phoenix
    "cbd_points": [(33.4484, -112.0740)],   # Downtown Phoenix (Washington & Central)
    # memphis
    "cbd_points": [(35.1495, -90.0490)],    # Downtown Memphis (Civic Center Plaza)
    # los_angeles
    "cbd_points": [(34.0537, -118.2427)],   # Los Angeles City Hall
    # dallas — dual CBD (min distance is taken over both)
    "cbd_points": [
        (32.7767, -96.7970),                # Dallas City Hall
        (32.7555, -97.3308),                # Downtown Fort Worth (Sundance Square)
    ],
    # denver
    "cbd_points": [(39.7392, -104.9903)],   # Denver City & County Building
    # atlanta
    "cbd_points": [(33.7537, -84.3901)],    # Five Points, Downtown Atlanta
    # chicago
    "cbd_points": [(41.8837, -87.6318)],    # Chicago City Hall (the Loop)
    # seattle
    "cbd_points": [(47.6038, -122.3301)],   # Seattle City Hall
    # miami
    "cbd_points": [(25.7743, -80.1937)],    # Downtown Miami (Government Center)
    #   NOTE: deliberately NOT Miami City Hall, which is in Coconut Grove.
```

(Each line goes inside its metro's dict — the comments above show which metro each belongs to.)

The offline CONUS-range test catches transposed/garbled coordinates; the design's geometric verification (CBD actually inside its CBSA) is enforced at rebuild time by `scripts/rebuild_gate.py`'s `min(distance_to_cbd_km) < 3 km` check — a misplaced CBD makes every ZCTA far away and fails the gate.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/config.py tests/test_config.py
git commit -m "feat(config): per-metro CBD reference points (dual-CBD for DFW)"
```

---

### Task 7: Flow wiring + schema + manifest (32 → 35 columns)

**Files:**
- Modify: `src/pipelines/build.py` (imports; two tasks after `transit_density_task`; flow body Steps 6c/7/9)
- Modify: `src/pipelines/schema.py:6-14,27,48`
- Modify: `src/pipelines/manifest.py:12-22,52-65`
- Test: `tests/test_flow_structure.py`, `tests/test_manifest.py`, `tests/test_schema.py` (adapts automatically)

**Interfaces:**
- Consumes: everything produced in Tasks 2–6.
- Produces: `fetch_lodes_task`, `employment_features_task` importable from `src.pipelines.build`; final CSVs carry 35 columns; manifests carry `lodes_year` + `source_urls.lodes`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_flow_structure.py`, extend the structural test's task list and add an import-surface test:

```python
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
```

In `tests/test_manifest.py`, append:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_flow_structure.py tests/test_manifest.py -v`
Expected: new/changed tests FAIL with `ImportError: cannot import name 'fetch_lodes_task'` and `KeyError: 'lodes_year'`.

- [ ] **Step 3: Wire the pipeline**

**`src/pipelines/build.py`** — add to the import block (after the `.demographics` import):

```python
from .lodes import (
    LODES_YEAR,
    distance_to_cbd_km,
    fetch_metro_lodes,
    job_accessibility,
    states_for_counties,
    zcta_job_counts,
)
```

Add after `transit_density_task` (line ~91):

```python
@task(name="fetch_lodes", **NETWORK_RETRIES, **_CACHE)
def fetch_lodes_task(states: tuple, year: int):
    return fetch_metro_lodes(states, year)


@task(name="employment_features")
def employment_features_task(lodes_df, zctas_in_metro, tracts, cbd_points, utm_zone: int):
    """[ZCTA5CE, job_count, distance_to_cbd_km, job_accessibility] for the metro.

    distance frame is the base (covers every metro ZCTA); job counts are
    left-merged and filled to 0 (absence from WAC means zero jobs, not missing).
    """
    dist = distance_to_cbd_km(zctas_in_metro, cbd_points, utm_zone)
    counts = zcta_job_counts(lodes_df)
    access = job_accessibility(zctas_in_metro, tracts, lodes_df, utm_zone)
    out = (
        dist.merge(counts, on="ZCTA5CE", how="left")
        .merge(access, on="ZCTA5CE", how="left")
    )
    out["job_count"] = out["job_count"].fillna(0.0)
    return out
```

In the flow body: read the config key with the other config reads (after `ZIP_PREFIXES = ...`, line ~148):

```python
    CBD_POINTS = metro_config["cbd_points"]
```

Insert **Step 6c** after the Step 6b block (after `zcta_area_df = ...`, line ~255):

```python
    # Step 6c: Employment features from LEHD LODES (jobs by workplace block)
    logger.info("STEP 6c: Fetching LODES employment data...")
    lodes_states = states_for_counties(COUNTIES)
    lodes_df = fetch_lodes_task(lodes_states, LODES_YEAR)
    employment = employment_features_task(
        lodes_df, zctas_in_metro, tracts_in_counties, CBD_POINTS, UTM_ZONE
    )
    logger.info(f"Computed employment features for {len(employment)} ZCTAs")
```

Extend the Step 7 merge chain — after the `zcta_area_df` merge (line ~279), add:

```python
        .merge(
            employment,
            on="ZCTA5CE",
            how="left"  # Left join to keep all ZCTAs
        )
```

Replace the density block (lines ~282-284) with:

```python
    # Calculate population and job density (per km²)
    final_dataset["pop_density"] = final_dataset["total_pop"] / final_dataset["area_km2"]
    final_dataset["job_density"] = final_dataset["job_count"] / final_dataset["area_km2"]
    final_dataset = final_dataset.drop(columns=["area_km2", "job_count"])
```

In `column_order`, insert `'job_density'` directly after `'pop_density'`, and `'distance_to_cbd_km'`, `'job_accessibility'` directly after `'stops_per_km2'` (35 entries total).

**`src/pipelines/schema.py`** — append to `REQUIRED_COLUMNS`:

```python
    "job_density", "distance_to_cbd_km", "job_accessibility",
```

Change `_NON_NEGATIVE_COLUMNS` to:

```python
_NON_NEGATIVE_COLUMNS = [
    "ttw_total", "total_pop", "pop_density", "stops_per_km2", "zori",
    "job_density", "distance_to_cbd_km", "job_accessibility",
]
```

Update the docstring: `all 32 REQUIRED_COLUMNS` → `all 35 REQUIRED_COLUMNS`.

**`src/pipelines/manifest.py`** — add the import and source URL:

```python
from src.pipelines.lodes import LODES_YEAR
```

```python
_SOURCE_URLS = {
    ...existing entries unchanged...
    "lodes": f"https://lehd.ces.census.gov/data/lodes/LODES8 (WAC S000_JT00 {LODES_YEAR} + xwalk)",
}
```

In `build_manifest`'s returned dict, after `"acs_demographics_year"`:

```python
        "lodes_year": LODES_YEAR,
```

- [ ] **Step 4: Run the offline suite**

Run: `uv run pytest -v`
Expected: everything PASSES **except** `tests/test_schema.py::test_all_committed_datasets_pass_schema` (9 parametrized failures: committed CSVs are missing the 3 new columns). This is the expected red window — it closes in Task 8. `test_missing_column_rejected` / range tests adapt automatically (they build fixtures from `REQUIRED_COLUMNS`).

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/build.py src/pipelines/schema.py src/pipelines/manifest.py tests/test_flow_structure.py tests/test_manifest.py
git commit -m "feat(pipeline): wire LODES employment features into the flow; schema 32->35 + lodes provenance"
```

---

# Phase 2 — Rebuild all 9 metros behind the equivalence gate

### Task 8: Rebuild gate script + live rebuild + committed data refresh

**Files:**
- Create: `scripts/rebuild_gate.py`
- Modify: `data/final/final_zcta_dataset_*.csv` ×9, `data/final/*.manifest.json` ×9 (regenerated)

**Interfaces:**
- Consumes: the full pipeline from Phase 1; `CENSUS_API_KEY` in `.env`; network.
- Produces: 35-column committed datasets + manifests; `scripts/rebuild_gate.py` reusable for future rebuilds.

- [ ] **Step 1: Snapshot the committed baseline**

```bash
mkdir -p /tmp/hca_baseline && cp data/final/final_zcta_dataset_*.csv /tmp/hca_baseline/
```

- [ ] **Step 2: Write the gate script**

Create `scripts/rebuild_gate.py`:

```python
"""Rebuild equivalence gate: compare regenerated final CSVs against a baseline.

Usage: uv run python scripts/rebuild_gate.py /tmp/hca_baseline

Passes when, for every metro:
  1. Row count and ZCTA set are identical to baseline.
  2. Every shared column EXCEPT the live ones ({zori, period, stops_per_km2})
     is byte-identical (string-level compare — same standard the Prefect
     refactor was held to).
  3. New columns are sane: job_density >= 0; min(distance_to_cbd_km) < 3 km
     (some ZCTA contains the CBD); Spearman corr(job_accessibility,
     distance_to_cbd_km) < 0 (access falls with distance).
Live-column drift is REPORTED (max abs delta) but does not fail the gate.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr

LIVE_COLUMNS = {"zori", "period", "stops_per_km2"}
NEW_COLUMNS = {"job_density", "distance_to_cbd_km", "job_accessibility"}
FINAL_DIR = Path(__file__).resolve().parents[1] / "data" / "final"


def check_metro(baseline_csv: Path, new_csv: Path) -> list[str]:
    errors: list[str] = []
    base = pd.read_csv(baseline_csv, dtype=str)
    new = pd.read_csv(new_csv, dtype=str)

    if len(base) != len(new):
        errors.append(f"row count {len(base)} -> {len(new)}")
    if set(base["ZCTA5CE"]) != set(new["ZCTA5CE"]):
        errors.append("ZCTA set changed")
        return errors

    base = base.sort_values("ZCTA5CE").reset_index(drop=True)
    new = new.sort_values("ZCTA5CE").reset_index(drop=True)

    frozen = [c for c in base.columns if c not in LIVE_COLUMNS]
    for col in frozen:
        if not base[col].fillna("").equals(new[col].fillna("")):
            n_diff = int((base[col].fillna("") != new[col].fillna("")).sum())
            errors.append(f"frozen column '{col}' drifted in {n_diff} rows")

    for col in LIVE_COLUMNS - {"period"}:
        b = pd.to_numeric(base[col], errors="coerce")
        n = pd.to_numeric(new[col], errors="coerce")
        delta = (b - n).abs().max()
        print(f"    live drift {col}: max |delta| = {delta}")

    num = pd.read_csv(new_csv)
    if (num["job_density"] < 0).any():
        errors.append("job_density has negative values")
    if num["distance_to_cbd_km"].min() >= 3.0:
        errors.append(
            f"min distance_to_cbd_km = {num['distance_to_cbd_km'].min():.1f} km "
            "(>= 3 km — CBD point is likely misplaced)"
        )
    rho = spearmanr(num["job_accessibility"], num["distance_to_cbd_km"]).statistic
    if rho >= 0:
        errors.append(f"job_accessibility does not fall with CBD distance (rho={rho:.2f})")
    print(f"    accessibility-vs-distance Spearman rho = {rho:.3f}")
    return errors


def main() -> int:
    baseline_dir = Path(sys.argv[1])
    failures: dict[str, list[str]] = {}
    for baseline_csv in sorted(baseline_dir.glob("final_zcta_dataset_*.csv")):
        metro = baseline_csv.stem.replace("final_zcta_dataset_", "")
        print(f"== {metro}")
        errs = check_metro(baseline_csv, FINAL_DIR / baseline_csv.name)
        if errs:
            failures[metro] = errs
            for e in errs:
                print(f"    FAIL: {e}")
        else:
            print("    OK")
    if failures:
        print(f"\nGATE FAILED for {sorted(failures)}")
        return 1
    print("\nGATE PASSED: all frozen columns identical, new columns sane.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Note: `scipy` is already a transitive dependency (statsmodels/sklearn); verify with `uv run python -c "import scipy"`. If it is somehow absent, add `scipy>=1.11` to `pyproject.toml` dependencies.

- [ ] **Step 3: Rebuild one metro first (fast failure surface)**

```bash
METRO=phoenix uv run python run_pipeline.py
uv run python scripts/rebuild_gate.py /tmp/hca_baseline 2>&1 | sed -n '/== phoenix/,/OK\|FAIL/p'
```

(`run_pipeline.py` has no single-metro flag — without `--all` it builds the metro named by the `METRO` env var, defaulting to phoenix.)
Expected: phoenix section shows `OK` with reported live drift; every frozen ACS/TIGER column identical. **Other metros will FAIL at this point (still 32-column baselines) — only phoenix's section matters here.** Investigate any frozen-column drift before proceeding; do not continue on a red phoenix gate.

- [ ] **Step 4: Rebuild the remaining 8 metros**

```bash
uv run python run_pipeline.py --all
```

Expected: 9 successes (~5–15 min per metro; Prefect cache makes the phoenix re-run cheap). Then run the full gate:

```bash
uv run python scripts/rebuild_gate.py /tmp/hca_baseline
```

Expected: `GATE PASSED` and exit code 0.

- [ ] **Step 5: Offline verification + full suite**

```bash
uv run python run_pipeline.py --verify
uv run pytest -q
```

Expected: verify reports `OK <metro>` ×9; **full pytest green including `test_all_committed_datasets_pass_schema`** (the red window from Task 7 closes here).

- [ ] **Step 6: Commit data + gate script**

```bash
git add scripts/rebuild_gate.py data/final/
git commit -m "feat(data): rebuild all 9 metros with employment columns (35-col schema) behind equivalence gate"
```

- [ ] **Step 7: Open the Phase 1+2 PR**

```bash
git push -u origin feat/employment-center-variables
gh pr create --title "Employment-center variables: LODES pipeline + 35-column datasets" --body "$(cat <<'EOF'
Adds job_density, distance_to_cbd_km, and job_accessibility per the design in
docs/plans/2026-07-10-employment-center-variables-design.md (committed on this branch).

- New src/pipelines/lodes.py: LODES8 WAC 2021 fetch + exact block->ZCTA crosswalk
  aggregation, min-over-points CBD distance (dual-CBD DFW), gravity accessibility
  (10 km decay).
- Schema 32 -> 35 columns; manifests carry lodes provenance; all 9 datasets rebuilt.
- Rebuild gate (scripts/rebuild_gate.py): all frozen ACS/TIGER columns byte-identical
  to baseline; live-column (zori/OSM) drift reported; new-column sanity checks pass.

Analysis integration (RQ1-RQ3) follows in a separate PR.
EOF
)"
```

Watch CI to green (`gh pr checks --watch`). Merge per the usual review flow before starting Phase 3 (or continue on the branch if review is async — Phase 3 is code-only and does not conflict).

---

# Phase 3 — Analysis integration (append-only)

### Task 9: Fixture columns

**Files:**
- Modify: `tests/conftest.py:27-47`

**Interfaces:**
- Produces: `sample_zcta_df` fixture with `job_density`, `distance_to_cbd_km`, `job_accessibility` columns — feeds every RQ test in Tasks 10–12.

- [ ] **Step 1: Add the three columns**

In `tests/conftest.py`, inside the `sample_zcta_df` dict after `"pct_car"`:

```python
        "job_density": np.random.uniform(10.0, 2000.0, n).tolist(),
        "distance_to_cbd_km": np.random.uniform(1.0, 40.0, n).tolist(),
        "job_accessibility": np.random.uniform(1_000.0, 200_000.0, n).tolist(),
```

- [ ] **Step 2: Run the full suite (regression check)**

Run: `uv run pytest -q`
Expected: all green — `test_data_loader.py`'s shape-equality test auto-adapts (both sides use the fixture); loader passes extra columns through untouched.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: employment columns in the shared ZCTA fixture"
```

---

### Task 10: RQ1 — employment predictors in both models

**Files:**
- Modify: `src/models/rq1_housing_commute_tradeoff.py:73-74,88-106,146-147`
- Test: `tests/test_rq1.py`

**Interfaces:**
- Consumes: fixture from Task 9.
- Produces: `analyze_rq1` requires and uses the three new predictors; `RQ1Results.feature_names` includes them (appended AFTER existing names — `report_rq1` reads `params[2]` as the quadratic coefficient and `pvalues[1]` as commute, so existing positions must not shift).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rq1.py` (it already imports `pytest`, `analyze_rq1`, and the `sample_zcta_df` fixture is injected by name — no new imports needed):

```python
def test_analyze_rq1_includes_employment_features(sample_zcta_df) -> None:
    result = analyze_rq1(sample_zcta_df)
    for name in ("job_density", "distance_to_cbd_km", "job_accessibility"):
        assert name in result.feature_names
    # positional contract: commute stays first; quad keeps commute² at index 1
    assert result.model_quad["feature_names"][0] == "commute_min_proxy"
    assert result.model_quad["feature_names"][1] == "commute_min_proxy²"


def test_analyze_rq1_missing_employment_column_raises(sample_zcta_df) -> None:
    with pytest.raises(ValueError, match="job_density"):
        analyze_rq1(sample_zcta_df.drop("job_density"))
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_rq1.py -v`
Expected: both new tests FAIL (feature names absent; no ValueError raised).

- [ ] **Step 3: Implement (append-only)**

In `src/models/rq1_housing_commute_tradeoff.py`:

`required_cols` (line ~73):

```python
    required_cols = ['rent_to_income', 'commute_min_proxy', 'renter_share',
                     'vehicle_access', 'pop_density', 'job_density',
                     'distance_to_cbd_km', 'job_accessibility']
```

Array extraction (after `pop_density_per_km2 = ...`, line ~92):

```python
    job_density_per_km2 = df_clean['job_density'].to_numpy()
    dist_cbd_km = df_clean['distance_to_cbd_km'].to_numpy()
    job_access = df_clean['job_accessibility'].to_numpy()
```

Feature matrices — new features appended AFTER all existing ones:

```python
    feature_matrix_linear = np.column_stack([
        commute_time_min, renter_share_pct, vehicle_access_pct, pop_density_per_km2,
        job_density_per_km2, dist_cbd_km, job_access
    ])
    feature_names_linear = ['commute_min_proxy', 'renter_share', 'vehicle_access',
                            'pop_density', 'job_density', 'distance_to_cbd_km',
                            'job_accessibility']

    commute_squared = commute_time_min ** 2
    feature_matrix_quad = np.column_stack([
        commute_time_min, commute_squared, renter_share_pct,
        vehicle_access_pct, pop_density_per_km2,
        job_density_per_km2, dist_cbd_km, job_access
    ])
    feature_names_quad = ['commute_min_proxy', 'commute_min_proxy²', 'renter_share',
                          'vehicle_access', 'pop_density', 'job_density',
                          'distance_to_cbd_km', 'job_accessibility']
```

`model_df` select (line ~146):

```python
    model_df = df_clean.select(['ZCTA5CE', 'rent_to_income', 'commute_min_proxy',
                                 'renter_share', 'vehicle_access', 'pop_density',
                                 'job_density', 'distance_to_cbd_km',
                                 'job_accessibility'])
```

Also update the docstring's input-column list (line ~54-56) to name the three new columns.

- [ ] **Step 4: Run to verify green**

Run: `uv run pytest tests/test_rq1.py tests/test_reporting_output.py -v`
Expected: all PASS (reporting tables are generic over `feature_names`; the small-sample n<10k warning on the 20-row fixture is a warning, not an error).

- [ ] **Step 5: Commit**

```bash
git add src/models/rq1_housing_commute_tradeoff.py tests/test_rq1.py
git commit -m "feat(rq1): employment predictors in linear and quadratic models"
```

---

### Task 11: RQ2 — controls, job-access ANOVA

**Files:**
- Modify: `src/models/rq2_equity_analysis.py:100,143-146,407-411`
- Test: `tests/test_rq2.py`

**Interfaces:**
- Consumes: fixture from Task 9.
- Produces: interaction-model controls include the three new columns when present (presence-gated — RQ2 must still run without them); one new ANOVA (`job_accessibility` × `income_segment`); `report_rq2` labels it "Job Accessibility". Interaction p-value stays at index 3 (controls append after the 3 base terms).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rq2.py`:

```python
def test_rq2_interaction_includes_employment_controls(sample_zcta_df) -> None:
    result = analyze_rq2(sample_zcta_df)
    names = result.interaction_model['feature_names']
    for name in ("job_density", "distance_to_cbd_km", "job_accessibility"):
        assert name in names
    # base terms keep their positions (report reads pvalues[3] as the interaction)
    assert names[:3] == ['commute_min_proxy', 'low_income', 'commute*low_income']


def test_rq2_job_accessibility_anova_present(sample_zcta_df) -> None:
    result = analyze_rq2(sample_zcta_df)
    anova_vars = [ar.variable for ar in result.anova_results]
    assert 'job_accessibility' in anova_vars


def test_rq2_still_runs_without_employment_columns(sample_zcta_df) -> None:
    df = sample_zcta_df.drop(["job_density", "distance_to_cbd_km", "job_accessibility"])
    result = analyze_rq2(df)
    assert result.interaction_model is not None
    assert 'job_density' not in result.interaction_model['feature_names']
```

(If `ANOVAResult`'s field is named differently than `variable`, check `src/models/results.py` and match it — the existing `report_rq2` loop reads `ar.variable`.)

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_rq2.py -v`
Expected: first two new tests FAIL; the third PASSES (nothing consumed the columns yet — keep it as the presence-gating regression guard).

- [ ] **Step 3: Implement**

In `src/models/rq2_equity_analysis.py`, extend the controls list (line ~100):

```python
        for control_col in ['stops_per_km2', 'pct_car', 'pct_white', 'total_pop',
                            'job_density', 'distance_to_cbd_km', 'job_accessibility']:
```

Add the ANOVA after the `stops_per_km2` block (line ~143-146):

```python
        if 'job_accessibility' in df.columns:
            anova_results.append(
                anova_by_group(df, 'job_accessibility', 'income_segment', income_groups)
            )
```

In `report_rq2`'s `anova_names` dict (line ~407-411):

```python
    anova_names = {
        'rent_to_income': 'Rent Burden',
        'long45_share': 'Long Commute Share',
        'stops_per_km2': 'Transit Density',
        'job_accessibility': 'Job Accessibility',
    }
```

- [ ] **Step 4: Run to verify green**

Run: `uv run pytest tests/test_rq2.py tests/test_reporting_output.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/models/rq2_equity_analysis.py tests/test_rq2.py
git commit -m "feat(rq2): employment controls + job-accessibility ANOVA by income segment"
```

---

### Task 12: RQ3 — ACI regression candidates

**Files:**
- Modify: `src/models/rq3_aci_analysis.py:90`
- Test: `tests/test_rq3.py`

**Interfaces:**
- Consumes: fixture from Task 9.
- Produces: `RQ3Results.feature_names` includes the three new columns when present; RQ3 still runs without them. ACI definition itself unchanged; quantile regression reuses `feature_names` automatically.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rq3.py`:

```python
def test_rq3_includes_employment_candidates(sample_zcta_df) -> None:
    result = analyze_rq3(sample_zcta_df)
    for name in ("job_density", "distance_to_cbd_km", "job_accessibility"):
        assert name in result.feature_names


def test_rq3_still_runs_without_employment_columns(sample_zcta_df) -> None:
    df = sample_zcta_df.drop(["job_density", "distance_to_cbd_km", "job_accessibility"])
    result = analyze_rq3(df)
    assert result.aci_model is not None
    assert 'job_density' not in result.feature_names
```

- [ ] **Step 2: Run to verify the first fails**

Run: `uv run pytest tests/test_rq3.py -v`
Expected: `test_rq3_includes_employment_candidates` FAILS; the without-columns test PASSES (keep as regression guard).

- [ ] **Step 3: Implement**

In `src/models/rq3_aci_analysis.py`, extend the optional-candidates loop (line ~90):

```python
    for col in ['median_income', 'pct_transit', 'pct_drive_alone', 'total_pop',
                'job_density', 'distance_to_cbd_km', 'job_accessibility']:
```

- [ ] **Step 4: Run to verify green + full suite**

Run: `uv run pytest -q`
Expected: entire suite green.

- [ ] **Step 5: Commit + Phase 3 PR**

```bash
git add src/models/rq3_aci_analysis.py tests/test_rq3.py
git commit -m "feat(rq3): employment features as ACI regression candidates"
```

If Phase 1+2 merged already: this work should be on a fresh branch `feat/employment-analysis-integration` cut from updated `origin/main` (rebase/cherry-pick Tasks 9–12 commits if they were made on the old branch); open a PR titled "Analysis integration: employment variables in RQ1–RQ3". Otherwise stack it on the existing branch and note the dependency in the PR body.

---

# Phase 4 — Re-run analysis, refresh findings and docs

### Task 13: Full analysis re-run + findings refresh

**Files:**
- Modify: `docs/findings.md` (+ regenerated `data/processed/`, `figures/` — both gitignored)

**Interfaces:**
- Consumes: merged Phases 1–3; 35-column committed datasets.
- Produces: updated findings with a before/after model-fit comparison.

- [ ] **Step 1: Run the full analysis**

```bash
uv run python run_analysis.py --all
```

Expected: 9 metros complete; per-metro `analysis_summary_{METRO}.md` files regenerate under `data/processed/{METRO}/`.

- [ ] **Step 2: Build the before/after comparison table**

Old values come from the current `docs/findings.md` RQ1 table (§3: Adj R² per metro) and ACI table (§5: ACI Adj R²). New values come from each regenerated `data/processed/{METRO}/analysis_summary_{METRO}.md` (RQ1 model-selection section and RQ3 ACI OLS section). Add this table to `docs/findings.md` as a new section "§9 Employment-Variable Impact (2026-07)":

```markdown
| Metro | RQ1 Adj R² (before) | RQ1 Adj R² (after) | ACI Adj R² (before) | ACI Adj R² (after) |
|-------|--------------------:|-------------------:|--------------------:|-------------------:|
| Phoenix | 0.315 | <from re-run> | 0.017 | <from re-run> |
| ... one row per metro, before-values copied from §3/§5 ...
```

with a caveat paragraph below it:

```markdown
RQ1 comparisons are drift-free (all predictors are ACS/TIGER/LODES-derived,
byte-identical or newly added). ACI comparisons confound the new employment
variables with zori/OSM drift from the 2026-07 rebuild (drift magnitudes
recorded in the rebuild gate output on PR #<Phase-1+2 PR number>).
```

- [ ] **Step 3: Update the affected findings sections**

Re-read the regenerated summaries and revise, minimally:
- §3 RQ1 table (model, Adj R², commute significance) — refresh values, keep format.
- §5 ACI table — refresh values; note where `job_accessibility`/`distance_to_cbd_km` are significant and their signs.
- §6 cross-cutting themes and §8 future directions — update only claims the new numbers contradict (e.g., if Phoenix stops being "essentially unexplainable", say what changed); mark "incorporate employment center locations" as done, pointing to §9.
- Keep the 2026-03-07 header date and add a "Revised: 2026-07 (employment variables)" line.

- [ ] **Step 4: Commit**

```bash
git add docs/findings.md
git commit -m "docs: refresh findings with employment-variable results + before/after comparison"
```

---

### Task 14: README + pipeline docs

**Files:**
- Modify: `README.md`, `RUNNING_PIPELINE.md`, `src/pipelines/PIPELINE_README.md`

- [ ] **Step 1: README**

- Data Sources table (~line 50-58): add row —
  `| LEHD LODES8 (WAC 2021) | ZCTA job density, CBD distance, gravity job accessibility | https://lehd.ces.census.gov/data/ | Public domain; UI-covered + federal jobs only (no self-employed/military) |`
  (match the table's actual column set).
- Pipeline Output Schema section: change "~30 columns" to "35 columns"; add three rows to the column table under a new "Employment" category:
  - `job_density` — jobs per km² (LODES WAC C000 / ZCTA UTM area) — LEHD LODES
  - `distance_to_cbd_km` — km from ZCTA centroid to nearest metro CBD point (dual-CBD for DFW) — derived (config CBD points)
  - `job_accessibility` — gravity index: Σ jobs·exp(−d/10 km) over metro tracts — LEHD LODES + TIGER
- Data Pipeline Flow mermaid: add a step node between transit density and the final merge: `LODES employment features` feeding the merge node.
- High-Level Architecture mermaid: add `lodes.py` beside the other `src/pipelines` modules.

- [ ] **Step 2: RUNNING_PIPELINE.md**

- Rewrite the "### Output Schema (32 columns)" section to "(35 columns)" listing all 35 columns in `column_order` order (the existing table is stale — it lists only 30; rebuild it from `src/pipelines/build.py` `column_order` with one line per column and a short description, using the README descriptions for the new three).
- Update the per-metro "Expected outputs: {N} ZCTAs × 32 columns" lines to "× 35 columns".
- Add "Step 6c: LODES employment features" to the numbered step list.

- [ ] **Step 3: PIPELINE_README.md**

- Add the three columns to its Output Schema table.
- Add the LODES fetch/compute to its step list (before "Reorder columns").

- [ ] **Step 4: Verify docs claims**

```bash
grep -rn "32 col\|~30 col\|32 REQUIRED" README.md RUNNING_PIPELINE.md src/pipelines/PIPELINE_README.md src/pipelines/schema.py
```

Expected: no stale hits.

- [ ] **Step 5: Commit + Phase 4 PR**

```bash
git add README.md RUNNING_PIPELINE.md src/pipelines/PIPELINE_README.md
git commit -m "docs: 35-column schema, LODES source, employment-feature pipeline step"
```

Open the Phase 4 PR (with Task 13's commit): "Findings + docs refresh: employment variables". After merge, archive both plan documents per repo convention:

```bash
git mv docs/plans/2026-07-10-employment-center-variables-design.md docs/plans/2026-07-10-employment-center-variables-plan.md docs/archive/
git commit -m "chore: archive implemented employment-center-variables design + plan"
```

---

## Verification Summary (per phase)

| Phase | Gate |
|-------|------|
| 1 | `uv run pytest` green except the 9 expected `test_all_committed_datasets_pass_schema` failures; `uv run ruff check src/ tests/` clean |
| 2 | `scripts/rebuild_gate.py` GATE PASSED; `run_pipeline.py --verify` OK ×9; full pytest green; CI green on PR |
| 3 | full pytest green; `uv run python run_analysis.py --metro PHX` smoke (metro codes: PHX/LA/DFW/MEM/DEN/ATL/CHI/SEA/MIA) |
| 4 | `run_analysis.py --all` completes ×9; no stale column-count strings; findings §9 complete |
