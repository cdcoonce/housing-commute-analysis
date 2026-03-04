# Plan: Test Suite Implementation

**Created:** 2026-03-03
**Review Reference:** `docs/reviews/2026-03-03_full_repo_review.md`
**Estimated Effort:** ~4–5 hours total
**Priority:** HIGH — Zero tests currently exist; this is the single biggest quality gap
**Depends on:** `docs/plans/quick_fixes_and_linting.md` (Tasks 1–3 minimum)

---

## Scope

The `tests/` directory contains only `__init__.py`. This plan creates a comprehensive test suite covering:

1. **Pure function unit tests** — functions with no I/O or network dependency
2. **Fixture-based integration tests** — loading real CSVs from `tests/fixtures/`
3. **Pipeline layer tests** — config validation, feature engineering, spatial logic
4. **Analysis layer tests** — models, preprocessing, reporting

### Out of Scope

- End-to-end pipeline runs (require Census API key + network)
- OSMnx/OpenStreetMap tests (require network + long runtime)
- Shapefile tests (require large test fixtures)

---

## Test Infrastructure

### Task 1: Configure pytest and Create Fixtures

**Files:**
- `pyproject.toml` — add `[tool.pytest.ini_options]`
- `tests/conftest.py` — shared fixtures
- `tests/fixtures/sample_final_zcta.csv` — minimal valid ZCTA dataset

**Step 1:** Add pytest config to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "slow: marks tests as slow (deselect with -m 'not slow')",
    "network: marks tests requiring network access (deselect with -m 'not network')",
]
filterwarnings = [
    "ignore::DeprecationWarning",
]
```

**Step 2:** Create `tests/conftest.py`:

```python
"""Shared test fixtures for housing-commute-analysis."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_zcta_df() -> pl.DataFrame:
    """Minimal valid ZCTA-level DataFrame for analysis tests.

    Contains 20 rows with all columns required by load_and_validate_data()
    and the RQ analysis modules.
    """
    np.random.seed(42)
    n = 20
    return pl.DataFrame({
        "ZCTA5CE": [f"8500{i}" for i in range(n)],
        "rent_to_income": np.random.uniform(0.15, 0.55, n).tolist(),
        "commute_min_proxy": np.random.uniform(15.0, 45.0, n).tolist(),
        "median_income": np.random.uniform(30000, 120000, n).tolist(),
        "median_rent": np.random.uniform(800, 2500, n).tolist(),
        "stops_per_km2": np.random.uniform(0.0, 5.0, n).tolist(),
        "renter_share": np.random.uniform(0.2, 0.8, n).tolist(),
        "vehicle_access": np.random.uniform(0.5, 0.98, n).tolist(),
        "pop_density": np.random.uniform(100, 5000, n).tolist(),
        "total_pop": np.random.randint(1000, 50000, n).tolist(),
        "pct_white": np.random.uniform(0.1, 0.8, n).tolist(),
        "pct_black": np.random.uniform(0.05, 0.4, n).tolist(),
        "pct_hispanic": np.random.uniform(0.05, 0.5, n).tolist(),
        "pct_asian": np.random.uniform(0.01, 0.2, n).tolist(),
        "zori": np.random.uniform(900, 2800, n).tolist(),
        "long45_share": np.random.uniform(0.05, 0.35, n).tolist(),
        "pct_transit": np.random.uniform(0.0, 0.3, n).tolist(),
        "pct_drive_alone": np.random.uniform(0.4, 0.9, n).tolist(),
        "pct_car": np.random.uniform(0.5, 0.95, n).tolist(),
    })


@pytest.fixture
def sample_zcta_csv(sample_zcta_df: pl.DataFrame, tmp_path: Path) -> Path:
    """Write sample ZCTA DataFrame to a temporary CSV file.

    Returns
    -------
    Path
        Path to the temp CSV file.
    """
    csv_path = tmp_path / "final_zcta_dataset_phoenix.csv"
    sample_zcta_df.write_csv(csv_path)
    return csv_path


@pytest.fixture
def numpy_X_y() -> tuple[np.ndarray, np.ndarray]:
    """Simple X/y pair for regression model tests.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        Feature matrix (50×3) and target (50,).
    """
    np.random.seed(42)
    X = np.random.randn(50, 3)
    y = 0.5 + 1.2 * X[:, 0] - 0.8 * X[:, 1] + 0.3 * X[:, 2] + np.random.randn(50) * 0.5
    return X, y
```

**Step 3:** Create a static CSV fixture `tests/fixtures/sample_final_zcta.csv`. This is generated once by writing the `sample_zcta_df` fixture to disk. Alternatively, depend entirely on the programmatic fixture above (recommended for simplicity).

### Verify

- `uv run pytest --collect-only` discovers fixtures and shows 0 tests
- No import errors

---

## Unit Tests: Models Layer

### Task 2: Test `src/models/models.py`

**File:** `tests/test_models.py`
**Priority:** HIGH — These are the core statistical functions

```python
"""Tests for src/models/models.py — regression utilities."""
```

#### Tests to write:

| Test | Function | What it verifies |
|------|----------|-----------------|
| `test_fit_ols_robust_returns_dict` | `fit_ols_robust` | Return type is dict with all expected keys |
| `test_fit_ols_robust_adj_r2_range` | `fit_ols_robust` | adj_r2 is in [0, 1] for well-behaved data |
| `test_fit_ols_robust_params_length` | `fit_ols_robust` | params length == n_features + 1 (constant) |
| `test_fit_ols_robust_mismatched_shapes` | `fit_ols_robust` | Raises `ValueError` when X.shape[0] != y.shape[0] |
| `test_fit_ols_robust_feature_names` | `fit_ols_robust` | Returned `feature_names` matches input + 'const' |
| `test_cv_rmse_returns_median_and_folds` | `cv_rmse` | Returns tuple of (float, list) with k elements |
| `test_cv_rmse_k_less_than_2` | `cv_rmse` | Raises `ValueError` for k=1 |
| `test_cv_rmse_mismatched_shapes` | `cv_rmse` | Raises `ValueError` when shapes mismatch |
| `test_cv_rmse_reproducibility` | `cv_rmse` | Same random_state gives same RMSE |
| `test_calculate_vif_returns_dataframe` | `calculate_vif` | Returns DataFrame with 'Feature' and 'VIF' columns |
| `test_calculate_vif_uncorrelated` | `calculate_vif` | VIF ≈ 1.0 for independent random columns |
| `test_calculate_vif_highly_correlated` | `calculate_vif` | VIF >> 10 for nearly collinear features |
| `test_fit_quantile_regression_invalid_tau` | `fit_quantile_regression` | Raises `ValueError` for tau=0 or tau=1 |

---

### Task 3: Test `src/models/preprocessing.py`

**File:** `tests/test_preprocessing.py`
**Priority:** HIGH — Used by all three RQ modules

#### Tests to write:

| Test | Function | What it verifies |
|------|----------|-----------------|
| `test_zscore_mean_zero_std_one` | `zscore` | Output mean ≈ 0.0, std ≈ 1.0 |
| `test_zscore_constant_series` | `zscore` | Returns zeros when all values are identical |
| `test_zscore_empty_series` | `zscore` | Handles empty series (no crash) |
| `test_standardize_features_creates_z_cols` | `standardize_features` | New `_z` columns added for each feature |
| `test_standardize_features_preserves_originals` | `standardize_features` | Original columns unchanged |
| `test_standardize_features_empty_list` | `standardize_features` | Raises `ValueError` |
| `test_standardize_features_missing_column` | `standardize_features` | Logs warning, skips missing columns |
| `test_standardize_features_zero_variance` | `standardize_features` | Skips cols with zero std, logs warning |
| `test_create_income_segments_terciles` | `create_income_segments` | Creates Low/Medium/High with ~33% each |
| `test_create_income_segments_already_exists` | `create_income_segments` | Returns unchanged if column exists |
| `test_create_income_segments_missing_income` | `create_income_segments` | Returns unchanged if income_col missing |
| `test_compute_majority_race_assigns_max` | `compute_majority_race` | Picks column with highest percentage |
| `test_compute_majority_race_handles_nulls` | `compute_majority_race` | Null race values → default behavior |
| `test_compute_majority_race_insufficient_cols` | `compute_majority_race` | Returns unchanged if < 2 race cols |

---

### Task 4: Test `src/models/data_loader.py`

**File:** `tests/test_data_loader.py`
**Priority:** MEDIUM — Wrapper around Polars `read_csv` with validation

#### Tests to write:

| Test | Function | What it verifies |
|------|----------|-----------------|
| `test_load_and_validate_data_valid` | `load_and_validate_data` | Returns DataFrame with expected shape |
| `test_load_and_validate_data_invalid_metro` | `load_and_validate_data` | Raises `ValueError` for 'NYC' |
| `test_load_and_validate_data_missing_file` | `load_and_validate_data` | Raises `FileNotFoundError` |
| `test_load_and_validate_data_drops_nulls` | `load_and_validate_data` | Rows with critical nulls are dropped |
| `test_load_and_validate_data_missing_cols` | `load_and_validate_data` | Raises `ValueError` if critical columns absent |

---

### Task 5: Test `src/models/reporting.py`

**File:** `tests/test_reporting.py`
**Priority:** MEDIUM

#### Tests to write:

| Test | Function | What it verifies |
|------|----------|-----------------|
| `test_save_markdown_table_creates_file` | `save_markdown_table` | File created with table content |
| `test_save_markdown_table_appends` | `save_markdown_table` | Existing content preserved on append |
| `test_save_markdown_table_empty_data` | `save_markdown_table` | Raises `ValueError` for empty dict |
| `test_save_markdown_table_mismatched_lengths` | `save_markdown_table` | Raises `ValueError` for uneven columns |
| `test_save_markdown_table_format` | `save_markdown_table` | Output matches GFM table syntax (pipe-separated) |
| `test_create_analysis_summary_header` | `create_analysis_summary_header` | Creates file with metro name and sample size |
| `test_append_section` | `append_section` | Appends ## heading with separator |

---

## Unit Tests: Pipeline Layer

### Task 6: Test `src/pipelines/config.py`

**File:** `tests/test_config.py`
**Priority:** MEDIUM — Catches config drift and duplicate entries

#### Tests to write:

| Test | Function | What it verifies |
|------|----------|-----------------|
| `test_all_metros_have_required_keys` | `METRO_CONFIGS` | Every metro has cbsa_code, counties, zip_prefixes, utm_zone, name |
| `test_no_duplicate_county_fips` | `METRO_CONFIGS` | No metro has duplicate (state, county) pairs |
| `test_cbsa_codes_are_valid` | `METRO_CONFIGS` | All CBSA codes are 5 digits |
| `test_utm_zones_are_valid_epsg` | `METRO_CONFIGS` | All utm_zone values >= 32601 |
| `test_census_api_key_loaded` | `CENSUS_API_KEY` | Key is not None (requires .env) — mark `@pytest.mark.skipif` if no .env |

---

### Task 7: Test `src/pipelines/acs.py` — Pure Functions Only

**File:** `tests/test_acs.py`
**Priority:** MEDIUM — Feature engineering logic is testable without network

#### Tests to write:

| Test | Function | What it verifies |
|------|----------|-----------------|
| `test_compute_acs_features_commute_proxy` | `compute_acs_features` | `commute_min_proxy` is weighted average in [0, 90] |
| `test_compute_acs_features_rent_to_income` | `compute_acs_features` | `rent_to_income` = median_rent / (median_income / 12) |
| `test_compute_acs_features_mode_shares_sum` | `compute_acs_features` | Mode shares sum to ≈ 1.0 |
| `test_compute_acs_features_negative_handled` | `compute_acs_features` | Census null codes (< 0) replaced with NaN |
| `test_fetch_acs_invalid_fips` | `fetch_acs_for_county` | Raises `ValueError` for bad state FIPS |
| `test_fetch_acs_invalid_year` | `fetch_acs_for_county` | Raises `ValueError` for year not in AVAILABLE_ACS_YEARS |

**Note:** To test `compute_acs_features()` without network, create a fixture DataFrame mimicking raw Census API output with correct column names.

---

### Task 8: Test `src/pipelines/demographics.py` — Pure Functions Only

**File:** `tests/test_demographics.py`
**Priority:** LOW

#### Tests to write:

| Test | Function | What it verifies |
|------|----------|-----------------|
| `test_compute_demographic_percentages` | `compute_demographic_percentages` | Pct columns sum to ~100% |
| `test_compute_demographic_percentages_zero_pop` | `compute_demographic_percentages` | Handles zero total_pop without division error |
| `test_fetch_demographics_invalid_fips` | `fetch_demographics_for_county` | Raises `ValueError` for bad FIPS |

---

### Task 9: Test `src/pipelines/utils.py`

**File:** `tests/test_utils.py`
**Priority:** LOW — After Plan 2 adds retry logic, test the retry configuration

#### Tests to write (post-Plan 2):

| Test | Function | What it verifies |
|------|----------|-----------------|
| `test_get_session_has_retry` | `_get_session` | Session adapters configured with Retry |
| `test_get_session_mounts_https` | `_get_session` | Session has HTTPS adapter mounted |
| `test_esri_geojson_to_gdf_valid` | `esri_geojson_to_gdf` | Returns GeoDataFrame from valid ESRI JSON |
| `test_esri_geojson_to_gdf_empty_features` | `esri_geojson_to_gdf` | Returns empty GeoDataFrame for empty feature set |

---

## Execution Order

1. **Task 1** — Set up pytest config and fixtures
2. **Task 2** — `test_models.py` (13 tests, highest ROI — core stats functions)
3. **Task 3** — `test_preprocessing.py` (14 tests, second highest ROI)
4. **Task 4** — `test_data_loader.py` (5 tests)
5. **Task 5** — `test_reporting.py` (7 tests)
6. **Task 6** — `test_config.py` (5 tests)
7. **Task 7** — `test_acs.py` (6 tests)
8. **Task 8** — `test_demographics.py` (3 tests)
9. **Task 9** — `test_utils.py` (4 tests, depends on Plan 2)

**Total:** ~57 tests

---

## Running Tests

```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov=src --cov-report=term-missing

# Skip network-dependent tests
uv run pytest -m "not network"

# Only models layer
uv run pytest tests/test_models.py tests/test_preprocessing.py tests/test_reporting.py

# Verbose with timing
uv run pytest -v --tb=short --durations=10
```

---

## Completion Criteria

- [ ] `uv run pytest` discovers and runs ≥ 50 tests
- [ ] All tests pass with exit code 0
- [ ] `uv run pytest --cov=src --cov-report=term-missing` shows ≥ 40% coverage on tested modules
- [ ] No test requires network access unless marked `@pytest.mark.network`
- [ ] All test functions have docstrings explaining what is being tested
- [ ] `tests/conftest.py` provides reusable fixtures used by ≥ 3 test modules
