# Plan: Quick Fixes and Linting Cleanup

**Created:** 2026-03-03
**Review Reference:** `docs/reviews/2026-03-03_full_repo_review.md`
**Estimated Effort:** ~30 minutes total
**Priority:** HIGH — Resolves all 5 critical errors and most linting warnings

---

## Scope

This plan covers small, independent fixes that can each be completed in under 5 minutes. These address review sections 1.1–1.5 (critical errors), 2.1–2.6 (linting warnings), 2.7 (hardcoded date), 3.5 (incomplete metro map), and 3.6 (`__init__.py` exports).

---

## Tasks

### Task 1: Fix Malformed Docstring in `create_zcta_shapefile.py`

**Review ref:** §1.4
**File:** `src/pipelines/create_zcta_shapefile.py` line 1

**Current:**
```python
"""
"""Create ZCTA shapefiles for each metro area.
```

**Target:**
```python
"""Create ZCTA shapefiles for each metro area.
```

Remove the empty `"""` on line 1. The resulting module docstring should be a single valid triple-quoted string. This fixes 59 ruff `invalid-syntax` parse errors.

**Verify:** `uv run ruff check src/pipelines/create_zcta_shapefile.py` returns no `invalid-syntax` errors.

---

### Task 2: Fix Broken Imports in `create_zcta_shapefile.py`

**Review ref:** §1.3
**File:** `src/pipelines/create_zcta_shapefile.py` lines 9–16

**Current:**
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import METRO_CONFIGS, PROJECT_ROOT, CBSA_CODE, SELECTED_METRO, METRO_NAME
from tiger import get_cbsa_polygon, get_state_zctas
from spatial import filter_zctas_in_cbsa
```

**Target:**
```python
from pathlib import Path

from .config import METRO_CONFIGS, PROJECT_ROOT, CBSA_CODE, SELECTED_METRO, METRO_NAME
from .tiger import get_cbsa_polygon, get_state_zctas
from .spatial import filter_zctas_in_cbsa
```

- Remove `sys` import and `sys.path.insert(...)` line entirely.
- Convert bare imports to relative imports (prefix with `.`).
- Remove `import sys` from the import block.

**Verify:** `python -c "from src.pipelines.create_zcta_shapefile import create_zcta_shapefile"` succeeds without import errors.

---

### Task 3: Remove Debug CSV Exports

**Review ref:** §1.2
**Files:**
- `src/pipelines/build.py` — line containing `tract_to_zcta_map.to_csv("data/test/debug_tract_to_zcta_map.csv"...)`
- `src/pipelines/zori.py` — line containing `zori_tidy.to_csv("data/test/debug_zori_tidy.csv"...)`

**Action:** Guard both lines behind `logger.isEnabledFor(logging.DEBUG)`:

```python
# build.py
if logger.isEnabledFor(logging.DEBUG):
    debug_path = PROJECT_ROOT / "data" / "test" / "debug_tract_to_zcta_map.csv"
    tract_to_zcta_map.to_csv(debug_path, index=False)
    logger.debug("Wrote debug tract-to-ZCTA map to %s", debug_path)
```

```python
# zori.py
if logger.isEnabledFor(logging.DEBUG):
    debug_path = Path("data/test/debug_zori_tidy.csv")
    zori_tidy.to_csv(debug_path, index=False)
    logger.debug("Wrote debug ZORI tidy data to %s", debug_path)
```

**Verify:** Run pipeline at INFO level — no debug CSVs should be written.

---

### Task 4: Fix Duplicate County in Atlanta Config

**Review ref:** §1.5
**File:** `src/pipelines/config.py` — atlanta counties list

**Current:**
```python
("13", "045"),  # GA - Cherokee
("13", "135"),  # GA - Gwinnett
("13", "151"),  # GA - Henry
("13", "057"),  # GA - Cherokee
```

**Action:** FIPS 13-045 = Carroll County, FIPS 13-057 = Cherokee County. The comment on `("13", "045")` is wrong. Fix the comment:

```python
("13", "045"),  # GA - Carroll
("13", "135"),  # GA - Gwinnett
("13", "151"),  # GA - Henry
("13", "057"),  # GA - Cherokee
```

Alternatively, if Carroll was not intended to be in the metro and Cherokee was: remove the `("13", "045")` entry entirely and keep only `("13", "057")`. The Atlanta-Sandy Springs-Alpharetta CBSA does **not** include Carroll County, so the correct fix is to **remove** `("13", "045")` and keep `("13", "057")`:

```python
("13", "121"),  # GA - Fulton
("13", "089"),  # GA - DeKalb
("13", "067"),  # GA - Cobb
("13", "063"),  # GA - Clayton
("13", "057"),  # GA - Cherokee
("13", "135"),  # GA - Gwinnett
("13", "151"),  # GA - Henry
```

**Decision required:** Verify whether Carroll County (13-045) is in the Atlanta CBSA. If not, remove it. If it is, fix the comment.

**Verify:** Run `METRO=atlanta python run_pipeline.py` and confirm tract counts are reasonable.

---

### Task 5: Run Ruff Auto-Fix

**Review ref:** §2.1–2.5, §6

**Command:**
```bash
uv run ruff check --fix src/ run_pipeline.py run_analysis.py
```

This auto-fixes:
- **W293** (635): Blank line whitespace
- **W291** (39): Trailing whitespace
- **W292** (7): Missing newline at end of file
- **F541** (16): f-strings without placeholders
- **I001** (4): Unsorted imports
- **F401** (1): Unused import (`Dict` in `preprocessing.py`)

**Post-fix:** Run `uv run ruff check src/ run_pipeline.py run_analysis.py` to confirm remaining issues are only E501 (line length) and E402 (intentional deferred import).

---

### Task 6: Add `# noqa: E402` to Intentional Deferred Import

**Review ref:** §2.6
**File:** `run_pipeline.py` line 49

**Current:**
```python
from src.pipelines.build import build_final_dataset
```

**Target:**
```python
from src.pipelines.build import build_final_dataset  # noqa: E402
```

---

### Task 7: Fix Hardcoded Analysis Date

**Review ref:** §2.7
**File:** `src/models/reporting.py` — `create_analysis_summary_header()` function

**Current:**
```python
f.write("Analysis Date: November 9, 2025\n\n")
```

**Target:**
```python
from datetime import date
...
f.write(f"Analysis Date: {date.today().strftime('%B %d, %Y')}\n\n")
```

Add `from datetime import date` to the module imports. Update the hardcoded string to use `date.today()`.

---

### Task 8: Complete `metro_shp_map` in `run_analysis.py`

**Review ref:** §3.5
**File:** `run_analysis.py` lines 145–149

**Current:**
```python
metro_shp_map = {
    'PHX': 'phoenix',
    'LA': 'los_angeles',
    'DFW': 'dallas',
    'MEM': 'memphis'
}
```

**Target:**
```python
metro_shp_map = {
    'PHX': 'phoenix',
    'LA': 'los_angeles',
    'DFW': 'dallas',
    'MEM': 'memphis',
    'DEN': 'denver',
    'ATL': 'atlanta',
    'CHI': 'chicago',
    'SEA': 'seattle',
    'MIA': 'miami',
}
```

---

### Task 9: Add `__all__` Exports to `__init__.py` Files

**Review ref:** §3.6
**Files:**
- `src/__init__.py`
- `src/pipelines/__init__.py`
- `src/models/__init__.py`

**Target `src/pipelines/__init__.py`:**
```python
"""Data ingestion and transformation pipelines."""

__all__ = [
    "build",
    "config",
    "acs",
    "demographics",
    "osm",
    "spatial",
    "tiger",
    "utils",
    "zori",
]
```

**Target `src/models/__init__.py`:**
```python
"""Statistical models and analysis modules."""

__all__ = [
    "data_loader",
    "models",
    "preprocessing",
    "reporting",
    "visualization",
    "rq1_housing_commute_tradeoff",
    "rq2_equity_analysis",
    "rq3_aci_analysis",
]
```

**Target `src/__init__.py`:**
```python
"""DAT490 Housing Affordability Analysis Package."""
```

---

## Completion Criteria

- [ ] `uv run ruff check src/ run_pipeline.py run_analysis.py` returns only E501 (line length) warnings
- [ ] `python -c "from src.pipelines.create_zcta_shapefile import create_zcta_shapefile"` succeeds
- [ ] No debug CSV files written during normal pipeline execution
- [ ] Atlanta county list matches official CBSA definition
- [ ] All 9 metros have shapefile auto-detection in `run_analysis.py`
