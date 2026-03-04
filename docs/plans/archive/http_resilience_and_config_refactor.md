# Plan: HTTP Resilience, Config Refactoring, and Data Consistency

**Created:** 2026-03-03
**Review Reference:** `docs/reviews/2026-03-03_full_repo_review.md`
**Estimated Effort:** ~2 hours total
**Priority:** MEDIUM — Improves pipeline reliability and data consistency
**Depends on:** `docs/plans/quick_fixes_and_linting.md` (Tasks 1–5 should be done first)

---

## Scope

This plan covers three interrelated improvements:
1. **HTTP retry/backoff** for Census, TIGER, and Zillow API calls (§4.2)
2. **Config refactoring** to eliminate `importlib.reload()` hack (§5.2)
3. **Income segmentation standardization** — resolve quartile-vs-tercile inconsistency (§2.8)
4. **Web Mercator → UTM** fix for area calculation in `osm.py` (§3.4)
5. **DRY cleanup** for repeated numeric column list in `acs.py` (§3.1)

---

## Task 1: Add HTTP Retry with Exponential Backoff

**Review ref:** §4.2
**Files:** `src/pipelines/utils.py`

### Problem

All three HTTP helper functions (`http_csv_to_df`, `http_json_to_dict`, `esri_geojson_to_gdf`) use bare `requests.get()`. A single transient failure (429, 500, 502, 503, 504, timeout) kills the entire pipeline run, which can be 30+ minutes into execution.

### Implementation

Create a module-level `requests.Session` with retry logic, then use it in all three functions.

**Step 1:** Add retry session factory at top of `utils.py`:

```python
"""Utility functions for HTTP requests and geospatial data parsing."""
from __future__ import annotations

import io
import logging

import geopandas as gpd
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from shapely.geometry import shape
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Retry configuration for external API requests
_RETRY_STRATEGY = Retry(
    total=3,                                    # Max 3 retries
    backoff_factor=1,                           # Wait 1s, 2s, 4s between retries
    status_forcelist=[429, 500, 502, 503, 504], # Retry on these HTTP codes
    allowed_methods=["GET"],                    # Only retry GET requests
    raise_on_status=False,                      # Let raise_for_status() handle errors
)


def _get_session() -> requests.Session:
    """Create a requests.Session with automatic retry and exponential backoff.

    Returns
    -------
    requests.Session
        Session configured with retry strategy for HTTPS requests.
    """
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=_RETRY_STRATEGY)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
```

**Step 2:** Replace all `requests.get(...)` calls with `_get_session().get(...)`:

- `http_csv_to_df()`: Replace `requests.get(url, timeout=timeout)` → `_get_session().get(url, timeout=timeout)`
- `http_json_to_dict()`: Replace `requests.get(url, params=params, timeout=180)` → `_get_session().get(url, params=params, timeout=180)`
- `esri_geojson_to_gdf()`: Replace `requests.get(url, params=params, timeout=180)` → `_get_session().get(url, params=params, timeout=180)`

**Step 3:** Also fix `src/pipelines/acs.py` — `fetch_acs_for_county()` makes its own `requests.get()` call (line 116). Import and use the session there too:

```python
from .utils import _get_session

# In fetch_acs_for_county():
response = _get_session().get(url, params=params, timeout=120)
```

### Verify

- `uv run python -c "from src.pipelines.utils import _get_session; print(_get_session())"` succeeds
- Manual test: disconnect network briefly during pipeline run, confirm retries appear in logs then succeed when network recovers

---

## Task 2: Refactor `build_final_dataset()` to Accept Config Parameter

**Review ref:** §5.2
**Files:** `src/pipelines/build.py`, `run_pipeline.py`

### Problem

`build_final_dataset()` uses `importlib.reload(config)` to re-read environment variables. This is fragile because:
- Module reload doesn't update variables already imported by other modules
- It's a hidden dependency on `os.environ["METRO"]` being set before the call
- It makes the function signature lie — it takes no arguments but depends on global state

### Implementation

**Step 1:** Change function signature to accept `metro_key`:

```python
def build_final_dataset(metro_key: str = "phoenix") -> str:
    """Execute the full data pipeline to build ZCTA-level housing dataset.

    Parameters
    ----------
    metro_key : str
        Key into METRO_CONFIGS (e.g., 'phoenix', 'dallas', 'atlanta').
        Defaults to 'phoenix'.

    Returns
    -------
    str
        Path to the output CSV file.
    """
    from .config import METRO_CONFIGS, DATA_FINAL, CACHE_DIR, ZORI_ZIP_CSV_URL

    metro_config = METRO_CONFIGS[metro_key]
    cbsa_code = metro_config["cbsa_code"]
    counties = metro_config["counties"]
    zip_prefixes = metro_config["zip_prefixes"]
    utm_zone = metro_config["utm_zone"]
    metro_name = metro_config["name"]
    final_zcta_out = DATA_FINAL / f"final_zcta_dataset_{metro_key}.csv"
    ...
```

**Step 2:** Remove the `importlib.reload(config)` block and all references to reloading.

**Step 3:** Pass `utm_zone` explicitly to `filter_zctas_in_cbsa()` and `tract_to_zcta_centroid_map()`.

Currently `spatial.py` reads `UTM_ZONE` from config at module level:
```python
from .config import UTM_ZONE
```

Change `filter_zctas_in_cbsa()` and `tract_to_zcta_centroid_map()` to accept `utm_zone` as a parameter:

```python
def filter_zctas_in_cbsa(
    zcta_gdf: gpd.GeoDataFrame,
    cbsa_gdf: gpd.GeoDataFrame,
    utm_zone: int = 32612,
) -> gpd.GeoDataFrame:
    ...
```

```python
def tract_to_zcta_centroid_map(
    tracts_gdf: gpd.GeoDataFrame,
    zctas_gdf: gpd.GeoDataFrame,
    utm_zone: int = 32612,
) -> pd.DataFrame:
    ...
```

**Step 4:** Update `run_pipeline.py`:

```python
# In run_single_metro():
def run_single_metro(metro: str) -> tuple[bool, str]:
    try:
        output_path = build_final_dataset(metro_key=metro)
        return True, str(output_path)
    ...
```

Remove the `os.environ["METRO"]` manipulation in `run_single_metro()`.

**Step 5:** Update the single-metro path in `main()`:

```python
# Single metro mode
metro = os.getenv("METRO", "phoenix")
...
output_path = build_final_dataset(metro_key=metro)
```

### Verify

- `METRO=dallas python run_pipeline.py` still works
- `python run_pipeline.py --all` processes all metros correctly
- No references to `importlib.reload` remain in codebase

---

## Task 3: Standardize Income Segmentation (Terciles Everywhere)

**Review ref:** §2.8
**Files:** `src/pipelines/demographics.py`, `src/models/preprocessing.py`, `src/pipelines/build.py`

### Problem

Two implementations of `create_income_segments()` exist:
- **Pipeline** (`src/pipelines/demographics.py`): Uses Q25/Q75 (quartile cuts) → Low/Medium/High
- **Analysis** (`src/models/preprocessing.py`): Uses Q33.3/Q66.7 (tercile cuts) → Low/Medium/High

Both produce a column named `income_segment` but with different boundaries. The pipeline version writes `income_segment` to the final CSV. The analysis modules then **overwrite it** with tercile-based segments in `rq2_equity_analysis.py` (conditionally, only when the column doesn't exist — which it does from the pipeline).

### Decision

Standardize on **terciles** (Q33/Q67) in both places. Terciles are more appropriate for splitting into three equal-sized groups, which is the stated intent in both docstrings.

### Implementation

**Step 1:** Update `src/pipelines/demographics.py` — `create_income_segments()`:

Change:
```python
q25 = result["median_income"].quantile(0.25)
q75 = result["median_income"].quantile(0.75)
```

To:
```python
q33 = result["median_income"].quantile(0.333)
q67 = result["median_income"].quantile(0.667)
```

And update the `assign_segment()` function and docstring accordingly:
```python
def assign_segment(income):
    if pd.isna(income):
        return None
    elif income < q33:
        return "Low"
    elif income <= q67:
        return "Medium"
    else:
        return "High"
```

Update the docstring to state "tercile" instead of "quartile" and reference Q33/Q67.

**Step 2:** Verify `src/models/preprocessing.py` already uses Q33/Q67 (it does — `TERCILE_LOW_QUANTILE = 0.333`, `TERCILE_HIGH_QUANTILE = 0.667`). No changes needed.

**Step 3:** Re-run the pipeline for one metro and confirm the `income_segment` distribution is roughly 33/33/33.

### Verify

- `METRO=phoenix python run_pipeline.py` produces `income_segment` values split ~33/33/33
- Analysis modules don't re-create the column (since it already exists with correct boundaries)

---

## Task 4: Use UTM Instead of Web Mercator for Area in `osm.py`

**Review ref:** §3.4
**File:** `src/pipelines/osm.py` — `zcta_transit_density()` function

### Problem

Area is calculated using EPSG:3857 (Web Mercator), which distorts area by up to 80% at high latitudes. The rest of the codebase uses UTM zones from config.

### Implementation

**Step 1:** Add `utm_zone` parameter to `zcta_transit_density()`:

```python
def zcta_transit_density(
    zcta_gdf: gpd.GeoDataFrame,
    transit_filter: str,
    fallback_filter: str,
    utm_zone: int = 32612,
) -> pd.DataFrame:
```

**Step 2:** Replace the Web Mercator area calculation:

```python
# BEFORE:
area_km2 = (
    gpd.GeoSeries(polygon, crs=4326)
    .to_crs(3857)
    .area
    .iloc[0] / 1_000_000
)

# AFTER:
area_km2 = (
    gpd.GeoSeries(polygon, crs=4326)
    .to_crs(utm_zone)
    .area
    .iloc[0] / 1_000_000
)
```

Also replace the transit features projection:
```python
# BEFORE:
if not transit_features.empty:
    transit_features = transit_features.to_crs(3857)

# AFTER:
if not transit_features.empty:
    transit_features = transit_features.to_crs(utm_zone)
```

**Step 3:** Update the call site in `build.py` to pass `utm_zone`:

```python
transit_density = zcta_transit_density(
    zctas_for_transit,
    transit_filter="",
    fallback_filter="",
    utm_zone=utm_zone,  # From metro config
)
```

### Verify

- Run for Phoenix (UTM 12N, low distortion from Web Mercator) and Seattle (UTM 10N, higher latitude) — compare `stops_per_km2` values before/after to confirm the change is directionally correct.

---

## Task 5: Extract Shared Numeric Column List in `acs.py`

**Review ref:** §3.1
**File:** `src/pipelines/acs.py`

### Problem

The identical list of ~30 numeric ACS column names is defined twice: once in `fetch_acs_for_county()` and once in `compute_acs_features()`.

### Implementation

**Step 1:** Add module-level constant after `ACS_VARS`:

```python
# Numeric ACS columns requiring type conversion (derived from ACS_VARS keys)
NUMERIC_ACS_COLS: list[str] = [
    "median_rent", "median_income", "ttw_total",
    "ttw_lt5", "ttw_5_9", "ttw_10_14", "ttw_15_19", "ttw_20_24",
    "ttw_25_29", "ttw_30_34", "ttw_35_39", "ttw_40_44",
    "ttw_45_59", "ttw_60_89", "ttw_90_plus",
    "mode_total", "mode_car_alone", "mode_carpool", "mode_transit",
    "mode_walk", "mode_other", "mode_wfh",
    "rent_burden_total", "rent_burden_30_34", "rent_burden_35_39",
    "rent_burden_40_49", "rent_burden_50_plus",
    "tenure_total", "tenure_owner", "tenure_renter",
    "vehicles_total", "vehicles_none", "vehicles_1", "vehicles_2_plus",
]
```

**Step 2:** Replace both inline lists with `NUMERIC_ACS_COLS`:

In `fetch_acs_for_county()`:
```python
for col in NUMERIC_ACS_COLS:
    acs_data[col] = pd.to_numeric(acs_data[col], errors="coerce")
```

In `compute_acs_features()`:
```python
for col in NUMERIC_ACS_COLS:
    features.loc[features[col] < 0, col] = pd.NA
```

### Verify

- `uv run python -c "from src.pipelines.acs import NUMERIC_ACS_COLS; print(len(NUMERIC_ACS_COLS))"` prints `30`
- Pipeline produces identical output CSV (diff before/after)

---

## Completion Criteria

- [ ] All `requests.get()` calls in `src/pipelines/` use retry-enabled session
- [ ] `build_final_dataset()` accepts `metro_key` parameter; no `importlib.reload()` in codebase
- [ ] `spatial.py` and `osm.py` functions accept `utm_zone` parameter
- [ ] Income segmentation uses terciles (Q33/Q67) in both pipeline and analysis
- [ ] `osm.py` uses UTM projection for area, not Web Mercator
- [ ] `acs.py` has single source of truth for numeric column list
- [ ] `python run_pipeline.py --all` runs successfully end-to-end
