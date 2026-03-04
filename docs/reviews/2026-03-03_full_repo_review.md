# Code Review: housing-commute-analysis

**Date:** 2026-03-03
**Reviewer:** GitHub Copilot (AI)
**Status:** ⚠ NEEDS IMPROVEMENT

---

## Summary

| Category | Errors | Warnings | Info |
| --- | --- | --- | --- |
| Linting (ruff) | 1 | 17 | 954 |
| Software Engineering | 5 | 8 | 6 |
| Security | 0 | 2 | 0 |
| Testing | 1 | 0 | 0 |
| Documentation | 0 | 3 | 2 |

**Files Reviewed:** 19 Python source files across `src/pipelines/`, `src/models/`, and root scripts.

---

## 1. Critical Issues (Must Fix)

### 1.1 ✗ ERROR — No Tests Exist

**Files:** `tests/` (empty except for `__init__.py`)

The entire codebase has **zero test coverage**. The `tests/` directory contains only an empty `__init__.py`. Given the project's CLAUDE.md explicitly mandates TDD and `uv run pytest`, this is a critical gap. Every public function in `src/pipelines/` and `src/models/` is untested.

**Impact:** Regressions go undetected. Refactoring is risky. Pipeline data quality is unverified.

**Recommendation:**
Priority test targets (highest value-to-effort ratio):
1. `src/pipelines/acs.py` — `compute_acs_features()`: test derived metric calculations (rent_to_income, commute bins, mode shares) with known input values.
2. `src/models/models.py` — `fit_ols_robust()`, `cv_rmse()`, `calculate_vif()`: test with synthetic data (known R², VIF).
3. `src/models/preprocessing.py` — `zscore()`, `standardize_features()`, `create_income_segments()`: pure functions ideal for unit testing.
4. `src/pipelines/demographics.py` — `compute_demographic_percentages()`, `create_income_segments()`: test percentage calculations and edge cases (zero population).
5. `src/models/data_loader.py` — `load_and_validate_data()`: test missing columns, missing files, null filtering.

### 1.2 ✗ ERROR — Debug Artifacts Committed to Main Code

**Files:** `src/pipelines/build.py` (line 103), `src/pipelines/zori.py` (line 63)

```python
# build.py line 103
tract_to_zcta_map.to_csv("data/test/debug_tract_to_zcta_map.csv", index=False)

# zori.py line 63
zori_tidy.to_csv("data/test/debug_zori_tidy.csv", index=False)
```

Debug CSV exports are hardcoded into the production pipeline. These use **relative paths** (fragile), write on every run (wasted I/O), and pollute `data/test/`.

**Fix:** Remove these lines or guard them behind a `DEBUG` flag or `logger.isEnabledFor(logging.DEBUG)` check.

### 1.3 ✗ ERROR — `create_zcta_shapefile.py` Uses Broken Import Pattern

**File:** `src/pipelines/create_zcta_shapefile.py` (lines 12–16)

```python
sys.path.insert(0, str(Path(__file__).parent))

from config import METRO_CONFIGS, PROJECT_ROOT, CBSA_CODE, SELECTED_METRO, METRO_NAME
from tiger import get_cbsa_polygon, get_state_zctas
from spatial import filter_zctas_in_cbsa
```

This script manipulates `sys.path` and uses bare imports instead of relative/absolute package imports. It will fail when invoked as a module (`python -m src.pipelines.create_zcta_shapefile`) and breaks IDE analysis.

**Fix:** Use relative imports (`from .config import ...`) and invoke via `python -m src.pipelines.create_zcta_shapefile` or add a proper entry point.

### 1.4 ✗ ERROR — Duplicate Module-level `__init__.py` Docstring Missing

**File:** `src/pipelines/create_zcta_shapefile.py` (line 1)

```python
"""
"""Create ZCTA shapefiles for each metro area.
```

The module docstring is malformed — it starts with `"""\n"""` (empty docstring followed by a new docstring). This causes a syntax-level parse issue (the 59 `invalid-syntax` ruff errors originate from this file).

**Fix:** Remove the empty `"""` on line 1 so the docstring reads:

```python
"""Create ZCTA shapefiles for each metro area.
...
"""
```

### 1.5 ✗ ERROR — Duplicate County in Atlanta Config

**File:** `src/pipelines/config.py` (lines 87–94)

```python
"atlanta": {
    ...
    "counties": [
        ("13", "121"),  # GA - Fulton
        ...
        ("13", "045"),  # GA - Cherokee
        ...
        ("13", "057"),  # GA - Cherokee   # <-- DUPLICATE / WRONG
    ],
```

County `("13", "057")` is labeled as Cherokee but FIPS 13-057 is actually **Cherokee** County while `("13", "045")` is **Carroll** County. The comment says both are Cherokee. One of these entries is either a duplicate or incorrect. FIPS 13-057 = Cherokee, FIPS 13-045 = Carroll.

**Fix:** Verify the intended counties. If Carroll County (13-045) should be included, update the comment. If Cherokee is listed twice, remove the duplicate.

---

## 2. Warnings (Should Fix)

### 2.1 ⚠ WARNING — Unused Import

**File:** `src/models/preprocessing.py` (line 9)

```python
from typing import Dict, List, Optional
```

`Dict` is imported but never used. Use `List` and `Optional` only, or switch to built-in generics (`list`, `dict`) since the project targets Python 3.11+.

### 2.2 ⚠ WARNING — 16 f-strings Without Placeholders

**Files:** `src/models/rq1_housing_commute_tradeoff.py`, `src/models/rq3_aci_analysis.py`

Multiple `f"..."` strings contain no `{...}` placeholders (e.g., `f"Linear Model Results:"`). These are wasteful and misleading.

**Fix:** Run `uv run ruff check --fix` to auto-remove extraneous `f` prefixes.

### 2.3 ⚠ WARNING — Import Order Violations (4 files)

Ruff found 4 `I001` (unsorted imports) violations. These can be auto-fixed with `uv run ruff check --fix`.

### 2.4 ⚠ WARNING — 210 Lines Exceed 88-Character Limit

Per project style (Black-compatible, max 88), 210 lines exceed the length limit. Most are in markdown `f.write()` strings and can be wrapped across multiple lines.

### 2.5 ⚠ WARNING — Missing Newline at End of File (7 files)

Seven files are missing a trailing newline. Auto-fixable with `uv run ruff check --fix`.

### 2.6 ⚠ WARNING — `run_pipeline.py` Module-Level Import Not at Top

**File:** `run_pipeline.py` (line 49)

```python
from src.pipelines.build import build_final_dataset
```

This import is deferred after `sys.path` manipulation and `load_dotenv()`. This is intentional but should be suppressed with a `# noqa: E402` comment to signal intent.

### 2.7 ⚠ WARNING — Hardcoded Analysis Date in Reporting

**File:** `src/models/reporting.py` (line 138)

```python
f.write("Analysis Date: November 9, 2025\n\n")
```

The analysis date is hardcoded as a string. Use `datetime.date.today()` for accuracy.

### 2.8 ⚠ WARNING — Non-Deterministic Column Order Risk

**File:** `src/models/rq2_equity_analysis.py` (line 85)

The `income_segment` column is conditionally created but the pipeline doesn't check if it already exists at the *pandas* pipeline level (`build.py` calls a pandas-based `create_income_segments()` while the analysis script uses a Polars-based one). Two different implementations of `create_income_segments` exist — one in `src/pipelines/demographics.py` (pandas) and one in `src/models/preprocessing.py` (Polars) — with different quantile boundaries (quartiles vs. terciles).

**Impact:** The pipeline writes `income_segment` using Q25/Q75 quartile cuts. The analysis modules create terciles using Q33/Q67. These produce **different segment boundaries** for the same data.

**Fix:** Standardize on one approach (recommended: terciles in both places) or rename to distinguish them (`income_quartile` vs. `income_tercile`).

---

## 3. Code Quality (Info / Consider Fixing)

### 3.1 ℹ INFO — DRY Violation: Repeated Numeric Column Lists in `acs.py`

**File:** `src/pipelines/acs.py`

The list of numeric columns is defined identically in both `fetch_acs_for_county()` (line 130) and `compute_acs_features()` (line 170). If a new variable is added to `ACS_VARS`, both lists must be updated.

**Fix:** Extract to a module-level constant `NUMERIC_ACS_COLS`.

### 3.2 ℹ INFO — DRY Violation: Repeated ANOVA Pattern in `rq2_equity_analysis.py`

**File:** `src/models/rq2_equity_analysis.py`

The identical pattern for extracting group data and running ANOVA is repeated four times (rent burden, commute share, transit density, race). Extract to a helper function:

```python
def _anova_by_group(df: pl.DataFrame, value_col: str, group_col: str, groups: list[str]) -> tuple[float | None, float | None]:
    """Run one-way ANOVA on value_col across groups."""
    ...
```

### 3.3 ℹ INFO — Long Functions Violate SRP

Several functions exceed 100 lines:

| Function | File | Lines |
| --- | --- | --- |
| `run_rq1()` | `rq1_housing_commute_tradeoff.py` | ~310 |
| `run_rq2()` | `rq2_equity_analysis.py` | ~430 |
| `run_rq3()` | `rq3_aci_analysis.py` | ~350 |
| `build_final_dataset()` | `build.py` | ~190 |

These orchestration functions do data prep, modeling, visualization, *and* markdown report writing. Consider splitting report generation into dedicated functions (e.g., `_write_rq1_report()`).

### 3.4 ℹ INFO — Web Mercator (EPSG:3857) Used for Area Calculation in `osm.py`

**File:** `src/pipelines/osm.py` (line 118)

```python
area_km2 = (
    gpd.GeoSeries(polygon, crs=4326)
    .to_crs(3857)
    .area
    .iloc[0] / 1_000_000
)
```

Web Mercator (EPSG:3857) distorts area significantly at latitudes far from the equator. The rest of the codebase uses UTM zones for area calculations (e.g., `build.py` line 140). For consistency and accuracy, use `UTM_ZONE` from config here as well.

### 3.5 ℹ INFO — `run_analysis.py` Incomplete `metro_shp_map`

**File:** `run_analysis.py` (lines 155–160)

```python
metro_shp_map = {
    'PHX': 'phoenix',
    'LA': 'los_angeles',
    'DFW': 'dallas',
    'MEM': 'memphis'
}
```

This map is missing 5 metros (DEN, ATL, CHI, SEA, MIA) that are otherwise fully supported. The shapefile auto-detection silently fails for these metros.

**Fix:** Add all 9 metros to `metro_shp_map`.

### 3.6 ℹ INFO — Missing `__all__` Exports in `__init__.py` Files

All three `__init__.py` files (`src/`, `src/pipelines/`, `src/models/`) contain only comments. Adding `__all__` lists clarifies the public API and supports IDE auto-import.

---

## 4. Security

### 4.1 ⚠ WARNING — Census API Key Exposed in Environment Variables

**File:** `src/pipelines/config.py` (line 11)

```python
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY", None)
```

The API key is read correctly from the environment, but `run_pipeline.py` logs whether it's set:

```python
logger.info(f"Census API Key: {'✓ Set' if os.getenv('CENSUS_API_KEY') else '✗ Not set'}")
```

This is acceptable, but ensure `.env` is in `.gitignore`. No credential leakage was found in committed files.

### 4.2 ⚠ WARNING — No Request Retry/Backoff for External APIs

**Files:** `src/pipelines/utils.py`, `src/pipelines/acs.py`, `src/pipelines/tiger.py`

All HTTP requests use bare `requests.get()` without retry logic. Census and TIGER APIs are rate-limited and intermittently fail. A single timeout or 429 response kills the entire pipeline.

**Fix:** Use `requests.adapters.HTTPAdapter` with `urllib3.util.Retry` or the `tenacity` library for exponential backoff:

```python
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retry))
```

---

## 5. Architecture & Design

### 5.1 Mixed DataFrame Libraries (pandas vs. Polars)

The pipeline layer (`src/pipelines/`) uses **pandas** and **geopandas** exclusively. The analysis layer (`src/models/`) uses **Polars** exclusively. This creates a conversion boundary at the interface between pipeline output (CSV) and analysis input.

This is acceptable for the current architecture (pipeline writes CSV, analysis reads CSV), but should be documented as an intentional design decision. The two `create_income_segments()` functions (one pandas, one Polars) are a symptom of this split.

### 5.2 Config Module Uses Global State with `importlib.reload()`

**File:** `src/pipelines/build.py` (lines 64–65)

```python
from . import config
importlib.reload(config)
```

The `build_final_dataset()` function reloads the config module at runtime to pick up environment variable changes between calls. This is fragile — module reload doesn't guarantee all consumers of the old module-level constants are updated.

**Recommendation:** Refactor `build_final_dataset()` to accept a metro config dict as a parameter instead of relying on module-level state:

```python
def build_final_dataset(metro_key: str = "phoenix") -> str:
    config = METRO_CONFIGS[metro_key]
    ...
```

### 5.3 Tight Coupling of Analysis + Report Writing

The `run_rq1()`, `run_rq2()`, and `run_rq3()` functions each combine statistical modeling with markdown report generation. This makes it impossible to re-run analysis without regenerating reports, or to change report format without modifying analysis code.

**Recommendation:** Return a results dataclass from each RQ function, and have a separate reporting step:

```python
@dataclass
class RQ1Results:
    model_linear: dict
    model_quad: dict
    best_model_name: str
    ...

def run_rq1(df, metro) -> RQ1Results: ...
def write_rq1_report(results: RQ1Results, out_dir, metro): ...
```

---

## 6. Ruff Linter Summary

| Rule | Count | Auto-fixable | Description |
| --- | --- | --- | --- |
| W293 | 635 | Yes | Blank line contains whitespace |
| E501 | 210 | No | Line too long (>88 chars) |
| W291 | 39 | Yes | Trailing whitespace |
| F541 | 16 | Yes | f-string without placeholders |
| W292 | 7 | Yes | Missing newline at end of file |
| I001 | 4 | Yes | Unsorted imports |
| E402 | 1 | No | Module import not at top |
| F401 | 1 | Yes | Unused import |

**Quick fix:** Run `uv run ruff check --fix src/ run_pipeline.py run_analysis.py` to auto-fix 524 of 972 issues (whitespace, imports, f-strings, newlines).

---

## 7. Positive Observations

- **Excellent docstrings**: Nearly every function has comprehensive NumPy-style docstrings with parameter types, return types, and detailed notes. This is well above average.
- **Good separation of concerns**: Pipeline layer cleanly separated from analysis layer. Config centralized in one module.
- **Proper input validation**: Functions like `fetch_acs_for_county()`, `fit_ols_robust()`, and `cv_rmse()` validate inputs early with descriptive error messages.
- **Logging throughout**: Consistent use of `logging` module (not `print()`) across all modules.
- **Meaningful variable names**: `commute_time_min`, `rent_to_income`, `feature_matrix_linear` — descriptive and clear throughout.
- **Multi-state metro support**: The pipeline correctly handles metros spanning multiple states (Memphis TN-MS-AR, Chicago IL-IN-WI).
- **Robust null handling**: Census null codes (negative values like -666666666) are properly handled in ACS data processing.
- **OSMnx version compatibility**: Transit density code handles both old and new OSMnx APIs gracefully.

---

## 8. Recommended Actions (Priority Order)

| Priority | Action | Effort |
| --- | --- | --- |
| 1 | Fix malformed docstring in `create_zcta_shapefile.py` (causes 59 parse errors) | 1 min |
| 2 | Run `uv run ruff check --fix` to auto-fix 524 whitespace/import issues | 1 min |
| 3 | Remove debug CSV exports from `build.py` and `zori.py` | 5 min |
| 4 | Fix duplicate Cherokee county in Atlanta config | 5 min |
| 5 | Add missing metros to `metro_shp_map` in `run_analysis.py` | 5 min |
| 6 | Standardize income segmentation (quartile vs. tercile) | 30 min |
| 7 | Add HTTP retry logic with exponential backoff | 30 min |
| 8 | Use UTM instead of Web Mercator for area in `osm.py` | 15 min |
| 9 | Write unit tests for core calculation functions | 2–4 hrs |
| 10 | Refactor long RQ functions to separate analysis from reporting | 2–3 hrs |

---

*Report generated by GitHub Copilot code review skill.*
