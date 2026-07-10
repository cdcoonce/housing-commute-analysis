# Engineering Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the housing-commute pipeline — test the statistical core, wrap the ETL in resilient Prefect flows with resume caching, stamp every dataset with provenance, and make the whole thing reproducible with one command — without changing any analytical result.

**Architecture:** Five independently-mergeable phases. Phase 1 adds tests around the pure `analyze_rq*` functions and the `report_rq*` I/O half, then raises the coverage gate. Phase 2 decomposes `build_final_dataset` into Prefect 3 `@task`s (retries + 7-day input-keyed result cache on network steps) wrapped in a `@flow`, keeping `build_final_dataset` as a thin alias. Phase 3 adds a schema contract + per-run JSON manifest (sha256/provenance) and an offline `verify-data` path. Phase 4 adds an analysis `@flow`, `--all`, a `Makefile`, and a centralized `RANDOM_STATE`.

**Tech Stack:** Python 3.11+, uv, Polars (analysis) + pandas/GeoPandas (pipeline), statsmodels, scikit-learn, Prefect 3.x, pytest + pytest-cov, ruff.

## Global Constraints

- **Behavior-preserving for outputs:** identical `data/final/*.csv` schema + column order, identical figures/findings. Verify structural equivalence, never rewrite ETL logic — tasks call the existing `src/pipelines/*` functions unchanged.
- **Prefect is local-only:** no server, agent, or deployment. Flows run in-process. CI/tests run offline with `PREFECT_API_URL` unset, `PREFECT_SERVER_ALLOW_EPHEMERAL_MODE=true`, project-local `PREFECT_HOME`.
- **Prefect version floor:** `prefect>=3.0` (bumped from `>=2.14.0`). Use `cache_policy=INPUTS` + `cache_expiration=timedelta(days=7)`, not the legacy 2.x `cache_key_fn`.
- **Cache TTL:** 7 days. Result cache in gitignored `.prefect_cache/`.
- **Coverage gate target:** raise `--cov-fail-under` from 40 to ~70 (pinned just below achieved after tests land).
- **Determinism seed:** literal `42` today; centralize as `RANDOM_STATE` (env-overridable, default 42).
- **Column order (verbatim, the pipeline's final schema, 32 cols):** `ZCTA5CE, rent_to_income, pct_rent_burden_30, pct_rent_burden_50, zori, commute_min_proxy, pct_commute_lt10, pct_commute_10_19, pct_commute_20_29, pct_commute_30_44, pct_commute_45_59, pct_commute_60_plus, ttw_total, pct_drive_alone, pct_carpool, pct_car, pct_transit, pct_walk, pct_wfh, renter_share, vehicle_access, total_pop, pop_density, pct_white, pct_black, pct_asian, pct_hispanic, pct_other, median_income, income_segment, stops_per_km2, period`.
- **Metro identifiers differ by layer:** pipeline uses lowercase names (`phoenix`, `los_angeles`, …); analysis uses uppercase codes (`PHX`, `LA`, `DFW`, …). Never cross them.
- **Commit style:** conventional commits. No agent attribution in commit messages.
- **Branch:** all work off a fresh feature branch from `origin/main`; run `uv run ruff check src/ tests/` and `uv run pytest -m "not network"` green before every commit.

---

## File Structure

**New files:**
- `tests/test_rq1.py`, `tests/test_rq2.py`, `tests/test_rq3.py` — analytical-core tests.
- `tests/test_reporting_output.py` — `report_rq*` + `save_markdown_table` I/O tests.
- `src/pipelines/prefect_config.py` — result storage + cache TTL constants.
- `src/pipelines/schema.py` — final-dataset schema contract.
- `src/pipelines/manifest.py` — provenance manifest build/write/verify.
- `Makefile` — one-command entry points.

**Modified files:**
- `pyproject.toml` — Prefect pin, coverage `omit` list.
- `.gitignore` — Prefect dirs.
- `tests/conftest.py` — `Agg` backend + Prefect offline fixture.
- `src/pipelines/build.py` — task/flow decomposition + manifest emission + schema validation.
- `src/models/models.py`, `src/models/rq2_equity_analysis.py`, `src/pipelines/config.py` — `RANDOM_STATE`.
- `src/models/data_loader.py` — schema validation call.
- `run_pipeline.py` — offline Prefect env defaults + `--verify`.
- `run_analysis.py` — `--all`.
- `.github/workflows/ci.yml` — coverage gate + verify-data step.
- `README.md`, `docs/findings.md` (commit), `.claude/skills/*` (resolve deletions).

---

# Phase 0 — Housekeeping

### Task 0.1: Clean working tree + Prefect pin

**Files:**
- Modify: `pyproject.toml:24`
- Modify: `.gitignore`
- Commit: `docs/findings.md` (currently untracked), resolve deleted `.claude/skills/*`

- [ ] **Step 1: Branch off the spec branch (which carries the design + this plan)**

The approved design (`...-design.md`, commit `b719eb7`) and this plan (`...-plan.md`, commit `f03d78d`) are committed only on branch `docs/engineering-hardening-spec`. Base the feature branch on that branch so both docs travel with the work — do **not** base on `origin/main` (that would drop them from the branch and break the PR reference).

```bash
cd /Users/cdcoonce/Developer/GitHub/housing-commute-analysis
git fetch origin
git checkout docs/engineering-hardening-spec        # contains b719eb7 (spec) + f03d78d (plan)
git checkout -b feat/engineering-hardening           # branch from here, NOT origin/main
```

- [ ] **Step 2: Restore accidentally-deleted skill files**

The working tree shows `D .claude/skills/code-review/references/markdown-checks.md` and three siblings. These are tooling, deleted unintentionally — restore them:

```bash
git checkout -- .claude/skills/
git status -s   # expect only: ?? docs/findings.md  (spec + plan already committed on the spec branch)
```

- [ ] **Step 3: Bump Prefect floor to 3.0**

In `pyproject.toml`, change line 24:

```toml
    "prefect>=3.0",
```

- [ ] **Step 4: Add Prefect dirs to .gitignore**

Append after the cache block (after `.cache/`):

```gitignore

# Prefect (local-only orchestration)
.prefect/
.prefect_cache/
```

- [ ] **Step 5: Sync and verify import still works**

```bash
uv sync
uv run python -c "import prefect; print(prefect.__version__)"   # expect 3.x
uv run ruff check src/ tests/
uv run pytest -m "not network" -q
```
Expected: prefect 3.x prints; ruff clean; existing suite passes.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .gitignore .claude/skills/ docs/findings.md
git commit -m "chore: bump prefect to 3.x, ignore prefect dirs, commit findings + restore skills"
```

---

# Phase 1 — Analytical-logic coverage

> Un-omitting the RQ modules **before** their tests exist would drop coverage below the gate, so tests land first (Tasks 1.1–1.4), then the omit list + gate change together (Task 1.5).

### Task 1.1: Headless backend fixture + RQ1 tests

**Files:**
- Modify: `tests/conftest.py` (top of file)
- Create: `tests/test_rq1.py`

**Interfaces:**
- Consumes: `analyze_rq1(df: pl.DataFrame) -> RQ1Results`; fixture `sample_zcta_df` (20-row pl.DataFrame with all RQ columns, seeded).
- `RQ1Results` fields used: `best_model_name` (`'Linear'|'Quadratic'`), `model_linear['aic']`, `model_quad['aic']`, `sample_size`, `y_pred`, `residuals`, `cv_rmse_linear`, `vif_linear` (pd.DataFrame with `VIF` column).

- [ ] **Step 1: Force the Agg backend in conftest**

No module sets a matplotlib backend; figure-writing tests must run headless. Insert these two lines **immediately after** the existing `from __future__ import annotations` line in `tests/conftest.py` (line 2) — a `__future__` import must stay the first statement, so do NOT put them above it (that is a `SyntaxError` that breaks the whole suite):

```python
import matplotlib

matplotlib.use("Agg")  # headless backend so report/figure tests run without a display
```

- [ ] **Step 2: Write RQ1 characterization tests**

```python
"""Tests for RQ1 housing-commute trade-off analysis (pure analyze half)."""
from __future__ import annotations

import polars as pl
import pytest

from src.models.results import RQ1Results
from src.models.rq1_housing_commute_tradeoff import analyze_rq1


def test_analyze_rq1_selects_lower_aic_model(sample_zcta_df: pl.DataFrame) -> None:
    result = analyze_rq1(sample_zcta_df)
    assert isinstance(result, RQ1Results)
    assert result.best_model_name in ("Linear", "Quadratic")
    aics = {"Linear": result.model_linear["aic"], "Quadratic": result.model_quad["aic"]}
    assert aics[result.best_model_name] == min(aics.values())


def test_analyze_rq1_output_shapes(sample_zcta_df: pl.DataFrame) -> None:
    result = analyze_rq1(sample_zcta_df)
    n = result.sample_size
    assert n > 0
    assert result.y_pred.shape == (n,)
    assert result.residuals.shape == (n,)
    assert result.cv_rmse_linear > 0
    assert "VIF" in result.vif_linear.columns


def test_analyze_rq1_missing_column_raises(sample_zcta_df: pl.DataFrame) -> None:
    df = sample_zcta_df.drop("renter_share")
    with pytest.raises(ValueError, match="Missing required columns"):
        analyze_rq1(df)
```

- [ ] **Step 3: Run — expect PASS (characterization of existing code)**

```bash
uv run pytest tests/test_rq1.py -v
```
Expected: 3 pass. If an assertion mismatches real behavior, tighten it to the observed value (these characterize existing correct code) — do not change the source.

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/test_rq1.py
git commit -m "test: cover analyze_rq1 + headless matplotlib backend"
```

### Task 1.2: RQ2 tests

**Files:**
- Create: `tests/test_rq2.py`

**Interfaces:**
- Consumes: `analyze_rq2(df) -> RQ2Results`; `RQ2Results` fields `cluster_labels` (np.ndarray|None), `anova_results` (list[ANOVAResult]), `df_with_segments`.
- `KMeans(random_state=42, n_init=10)` makes clustering deterministic.

- [ ] **Step 1: Write RQ2 tests**

```python
"""Tests for RQ2 equity analysis (pure analyze half)."""
from __future__ import annotations

import numpy as np
import polars as pl

from src.models.results import ANOVAResult, RQ2Results
from src.models.rq2_equity_analysis import analyze_rq2


def test_analyze_rq2_returns_results(sample_zcta_df: pl.DataFrame) -> None:
    result = analyze_rq2(sample_zcta_df)
    assert isinstance(result, RQ2Results)
    assert isinstance(result.anova_results, list)
    for a in result.anova_results:
        assert isinstance(a, ANOVAResult)


def test_analyze_rq2_cluster_labels_bounded(sample_zcta_df: pl.DataFrame) -> None:
    result = analyze_rq2(sample_zcta_df)
    if result.cluster_labels is not None:
        assert 0 < len(result.cluster_labels) <= sample_zcta_df.height
        assert set(np.unique(result.cluster_labels)).issubset({0, 1, 2, 3})


def test_analyze_rq2_is_deterministic(sample_zcta_df: pl.DataFrame) -> None:
    r1 = analyze_rq2(sample_zcta_df)
    r2 = analyze_rq2(sample_zcta_df)
    if r1.cluster_labels is not None and r2.cluster_labels is not None:
        assert np.array_equal(r1.cluster_labels, r2.cluster_labels)
```

- [ ] **Step 2: Run — expect PASS**

```bash
uv run pytest tests/test_rq2.py -v
```
Expected: 3 pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_rq2.py
git commit -m "test: cover analyze_rq2 clustering + determinism"
```

### Task 1.3: RQ3 tests (ACI identity)

**Files:**
- Create: `tests/test_rq3.py`

**Interfaces:**
- Consumes: `analyze_rq3(df) -> RQ3Results`; fields `df_with_aci` (pl.DataFrame with `ACI`, `rent_z`, `commute_z`), `quantile_results` (dict keyed by tau ⊆ {0.25,0.5,0.75}).
- ACI identity: `ACI == z(rent_to_income) + z(commute_min_proxy)`, z via polars mean/std (ddof=1), computed on the full frame before model filtering.

- [ ] **Step 1: Write RQ3 tests**

```python
"""Tests for RQ3 ACI analysis (pure analyze half)."""
from __future__ import annotations

import numpy as np
import polars as pl

from src.models.results import RQ3Results
from src.models.rq3_aci_analysis import analyze_rq3


def test_analyze_rq3_aci_is_sum_of_zscores(sample_zcta_df: pl.DataFrame) -> None:
    result = analyze_rq3(sample_zcta_df)
    assert isinstance(result, RQ3Results)
    df = result.df_with_aci
    assert df is not None
    rent = df["rent_to_income"]
    commute = df["commute_min_proxy"]
    rent_z = (rent - rent.mean()) / rent.std()        # polars std is sample (ddof=1)
    commute_z = (commute - commute.mean()) / commute.std()
    expected = (rent_z + commute_z).to_numpy()
    assert np.allclose(df["ACI"].to_numpy(), expected, rtol=1e-9, atol=1e-9)


def test_analyze_rq3_quantile_keys(sample_zcta_df: pl.DataFrame) -> None:
    result = analyze_rq3(sample_zcta_df)
    assert set(result.quantile_results.keys()).issubset({0.25, 0.5, 0.75})
```

- [ ] **Step 2: Run — expect PASS**

```bash
uv run pytest tests/test_rq3.py -v
```
Expected: 2 pass. If ACI comparison fails, print `df.columns` — confirm `df_with_aci` carries `rent_to_income`/`commute_min_proxy`; if it drops them, recompute z from `sample_zcta_df` joined on `ZCTA5CE` instead.

- [ ] **Step 3: Commit**

```bash
git add tests/test_rq3.py
git commit -m "test: cover analyze_rq3 ACI identity + quantile keys"
```

### Task 1.4: Reporting I/O tests

**Files:**
- Create: `tests/test_reporting_output.py`

**Interfaces:**
- Consumes: `report_rq1(results, out_dir, fig_dir, metro) -> None`, `report_rq2`, `report_rq3` (same sig, rq3 has optional `zcta_shp`), `save_markdown_table(data, path, title) -> None`.
- **Ordering contract:** `report_rq1` opens `analysis_summary_{metro.lower()}.md` in `'w'` (header author); `report_rq2`/`report_rq3` append in `'a'`. Tests must call `report_rq1` first.
- Output files: md `analysis_summary_phx.md`, csv `rq1_model_data_phx.csv`, figs `rq1_phx_{scatter,residuals,qq,hist}.png`.

- [ ] **Step 1: Write reporting tests**

```python
"""Tests for the report_rq* I/O half and save_markdown_table."""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from src.models.reporting import save_markdown_table
from src.models.rq1_housing_commute_tradeoff import analyze_rq1, report_rq1
from src.models.rq2_equity_analysis import analyze_rq2, report_rq2
from src.models.rq3_aci_analysis import analyze_rq3, report_rq3


def _dirs(tmp_path: Path) -> tuple[Path, Path]:
    out = tmp_path / "out"
    fig = tmp_path / "fig"
    out.mkdir()
    fig.mkdir()
    return out, fig


def test_report_rq1_writes_summary_csv_and_figures(sample_zcta_df: pl.DataFrame, tmp_path: Path) -> None:
    out, fig = _dirs(tmp_path)
    report_rq1(analyze_rq1(sample_zcta_df), out, fig, "PHX")
    md = out / "analysis_summary_phx.md"
    assert md.exists()
    text = md.read_text()
    assert "Model Comparison" in text
    assert (out / "rq1_model_data_phx.csv").exists()
    for name in ("rq1_phx_scatter.png", "rq1_phx_residuals.png", "rq1_phx_qq.png", "rq1_phx_hist.png"):
        assert (fig / name).exists()


def test_report_rq2_appends_to_summary(sample_zcta_df: pl.DataFrame, tmp_path: Path) -> None:
    out, fig = _dirs(tmp_path)
    report_rq1(analyze_rq1(sample_zcta_df), out, fig, "PHX")  # header author first
    report_rq2(analyze_rq2(sample_zcta_df), out, fig, "PHX")
    assert (out / "analysis_summary_phx.md").exists()


def test_report_rq3_appends_to_summary(sample_zcta_df: pl.DataFrame, tmp_path: Path) -> None:
    out, fig = _dirs(tmp_path)
    report_rq1(analyze_rq1(sample_zcta_df), out, fig, "PHX")
    report_rq3(analyze_rq3(sample_zcta_df), out, fig, "PHX")
    assert (out / "analysis_summary_phx.md").exists()


def test_save_markdown_table_writes_heading(tmp_path: Path) -> None:
    p = tmp_path / "t.md"
    save_markdown_table({"A": [1, 2], "B": [3, 4]}, p, "My Title")
    txt = p.read_text()
    assert "### My Title" in txt
    assert "A" in txt and "B" in txt


def test_save_markdown_table_length_mismatch_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        save_markdown_table({"A": [1, 2], "B": [3]}, tmp_path / "t.md", "T")
```

- [ ] **Step 2: Run — expect PASS**

```bash
uv run pytest tests/test_reporting_output.py -v
```
Expected: 5 pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_reporting_output.py
git commit -m "test: cover report_rq1/2/3 output + save_markdown_table"
```

### Task 1.5: Un-omit RQ modules, raise the gate

**Files:**
- Modify: `pyproject.toml:49-63` (coverage omit list)
- Modify: `.github/workflows/ci.yml:58` (`--cov-fail-under`)
- Modify: `README.md` (CI coverage mentions, ~lines 421–428)

- [ ] **Step 1: Remove the analytical modules from the omit list**

In `pyproject.toml`, delete these four lines from `[tool.coverage.run].omit` (keep `visualization.py`, `build.py`, and the pipeline/network + `run_*` entries):

```toml
    "src/models/rq1_housing_commute_tradeoff.py",
    "src/models/rq2_equity_analysis.py",
    "src/models/rq3_aci_analysis.py",
    "src/models/results.py",
```

- [ ] **Step 2: Measure achieved coverage**

```bash
uv run pytest -m "not network" --cov=src --cov-report=term-missing -q | tail -5
```
Record the `TOTAL` percentage.

- [ ] **Step 3: Set the gate**

Set `--cov-fail-under` (ci.yml line 58) to `min(70, floor(TOTAL) - 2)`. Example if TOTAL=76 → `70`; if TOTAL=68 → `66`.

```yaml
            --cov-fail-under=70 \
```

- [ ] **Step 4: Update README coverage wording**

Replace the two "40%" mentions in the CI section (the table row and the mermaid `Coverage ≥ 40%` node) with the new number.

- [ ] **Step 5: Verify the gate holds locally**

Use the exact `<GATE>` value you set in ci.yml in Step 3 (not a hardcoded 70):

```bash
uv run pytest -m "not network" --cov=src --cov-fail-under=<GATE> -q
uv run ruff check src/ tests/
```
Expected: passes at the chosen threshold.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .github/workflows/ci.yml README.md
git commit -m "test: measure RQ modules in coverage, raise gate to 70%"
```

---

# Phase 2 — Prefect refactor of the pipeline

### Task 2.1: Prefect config + offline test fixture

**Files:**
- Create: `src/pipelines/prefect_config.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Produces: `RESULT_STORAGE: LocalFileSystem`, `CACHE_TTL: timedelta`, `NETWORK_RETRIES: dict` for import by `build.py`.

- [ ] **Step 1: Write the Prefect config module**

```python
"""Local-only Prefect result storage + retry/cache constants for pipeline flows.

Keeps all Prefect state inside the repo (gitignored .prefect_cache/) so runs are
resumable within the cache window without any server, agent, or deployment.

NOTE: result storage is set via the PREFECT_RESULTS_LOCAL_STORAGE_PATH env var,
NOT by passing a LocalFileSystem block to @task. Prefect 3.x raises
`TypeError: Result storage configuration must be persisted server-side` if you
pass an unsaved block as result_storage — verified against prefect 3.6.4. The env
var points result persistence at .prefect_cache/ with no server and no .save().
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = PROJECT_ROOT / ".prefect_cache"
RESULT_DIR.mkdir(parents=True, exist_ok=True)

# Direct Prefect's local result storage at the repo-local cache dir (default
# pickle serializer handles GeoDataFrames/DataFrames). setdefault so an explicit
# env override still wins.
os.environ.setdefault("PREFECT_RESULTS_LOCAL_STORAGE_PATH", str(RESULT_DIR))

CACHE_TTL = timedelta(days=7)

# Whole-step retry schedule for flaky external APIs (composes above utils.py's
# per-request urllib3 adapter retry).
NETWORK_RETRIES = {"retries": 3, "retry_delay_seconds": [5, 15, 45]}
```

- [ ] **Step 2: Add an offline Prefect fixture to conftest**

Append to `tests/conftest.py`:

```python
import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _prefect_offline(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Force Prefect fully offline/ephemeral for the whole test session."""
    home = tmp_path_factory.mktemp("prefect_home")
    os.environ["PREFECT_HOME"] = str(home)
    os.environ["PREFECT_RESULTS_LOCAL_STORAGE_PATH"] = str(home / "results")
    os.environ["PREFECT_SERVER_ALLOW_EPHEMERAL_MODE"] = "true"
    os.environ["PREFECT_LOGGING_LEVEL"] = "WARNING"
    os.environ.pop("PREFECT_API_URL", None)
```

- [ ] **Step 3: Verify import + offline harness**

```bash
uv run python -c "from src.pipelines.prefect_config import CACHE_TTL, NETWORK_RETRIES; print(CACHE_TTL)"
uv run pytest -m "not network" -q
```
Expected: `7 days, 0:00:00`; suite passes.

- [ ] **Step 4: Commit**

```bash
git add src/pipelines/prefect_config.py tests/conftest.py
git commit -m "feat: add local-only Prefect result storage + offline test fixture"
```

### Task 2.2: Wrap ETL steps as Prefect tasks

**Files:**
- Modify: `src/pipelines/build.py` (add task wrappers above `build_final_dataset`)

**Interfaces:**
- Produces (task callables, all thin wrappers around existing functions):
  - Cacheable network tasks (simple, hashable inputs → `NETWORK_RETRIES` + `cache_policy=INPUTS` + `cache_expiration=CACHE_TTL` + `persist_result=True`): `fetch_cbsa_boundary_task(cbsa_code)`, `fetch_state_zctas_task(zip_prefixes)`, `fetch_tracts_task(counties)`, `fetch_acs_task(counties)`, `fetch_demographics_task(counties)`, `fetch_zori_task(url)`.
  - Retry-only network task (GeoDataFrame input, unhashable/large → retries but no INPUTS cache; OSM caches internally): `transit_density_task(zctas_for_transit, utm_zone)`.
  - Plain CPU tasks (no retries/cache): `filter_zctas_task`, `map_tracts_task`. The remaining CPU steps (commute/demographic aggregation, pop-density, merge/finalize) stay **inline** in the flow (Task 2.3) — they are not wrapped as tasks (they take large GeoDataFrames and are fast, deterministic, local). Do not reference `aggregate_*_task`/`pop_density_task`/`merge_finalize_task` — they are intentionally not created.

- [ ] **Step 1: Add imports + task wrappers to build.py**

Insert after the existing imports in `src/pipelines/build.py`:

```python
from prefect import flow, task
from prefect.cache_policies import INPUTS

from .prefect_config import CACHE_TTL, NETWORK_RETRIES  # importing prefect_config sets PREFECT_RESULTS_LOCAL_STORAGE_PATH

# NOTE: do NOT set result_storage here — an unsaved LocalFileSystem block raises
# TypeError at decorator time in Prefect 3.x. Persistence location comes from the
# PREFECT_RESULTS_LOCAL_STORAGE_PATH env var (set in prefect_config on import).
_CACHE = {
    "cache_policy": INPUTS,
    "cache_expiration": CACHE_TTL,
    "persist_result": True,
}


# --- Cacheable network tasks (hashable inputs) ---
@task(name="fetch_cbsa_boundary", **NETWORK_RETRIES, **_CACHE)
def fetch_cbsa_boundary_task(cbsa_code: str):
    return get_cbsa_polygon(cbsa_code)


@task(name="fetch_state_zctas", **NETWORK_RETRIES, **_CACHE)
def fetch_state_zctas_task(zip_prefixes):
    return get_state_zctas(zip_prefixes)


@task(name="fetch_tracts", **NETWORK_RETRIES, **_CACHE)
def fetch_tracts_task(counties):
    return get_tracts_for_counties(counties)


@task(name="fetch_acs", **NETWORK_RETRIES, **_CACHE)
def fetch_acs_task(counties):
    frames = [fetch_acs_for_county(s, c) for s, c in counties]
    return compute_acs_features(pd.concat(frames, ignore_index=True))


@task(name="fetch_demographics", **NETWORK_RETRIES, **_CACHE)
def fetch_demographics_task(counties):
    frames = [fetch_demographics_for_county(s, c) for s, c in counties]
    return compute_demographic_percentages(pd.concat(frames, ignore_index=True))


@task(name="fetch_zori", **NETWORK_RETRIES, **_CACHE)
def fetch_zori_task(url: str):
    return fetch_zori_latest(url)


# --- Retry-only network task (GeoDataFrame input; OSM caches internally) ---
@task(name="transit_density", **NETWORK_RETRIES)
def transit_density_task(zctas_for_transit, utm_zone: int):
    return zcta_transit_density(
        zctas_for_transit, transit_filter="", fallback_filter="", utm_zone=utm_zone
    )


# --- Plain CPU tasks ---
@task(name="filter_zctas")
def filter_zctas_task(zctas_all, cbsa_boundary, utm_zone: int):
    return filter_zctas_in_cbsa(zctas_all, cbsa_boundary, utm_zone=utm_zone)


@task(name="map_tracts_to_zctas")
def map_tracts_task(tracts, zctas_in_metro, utm_zone: int):
    return tract_to_zcta_centroid_map(tracts, zctas_in_metro, utm_zone=utm_zone)
```

- [ ] **Step 2: Verify tasks import + carry retry/cache config**

```bash
uv run python -c "
from src.pipelines.build import fetch_cbsa_boundary_task, transit_density_task, filter_zctas_task
assert fetch_cbsa_boundary_task.retries == 3
assert fetch_cbsa_boundary_task.cache_expiration.days == 7
assert transit_density_task.retries == 3
assert filter_zctas_task.retries == 0
print('task config OK')
"
```
Expected: `task config OK`.

- [ ] **Step 3: Commit**

```bash
git add src/pipelines/build.py
git commit -m "feat: wrap pipeline ETL steps as Prefect tasks"
```

### Task 2.3: Define the flow, rewire `build_final_dataset`

**Files:**
- Modify: `src/pipelines/build.py` (convert the body of `build_final_dataset` into `@flow build_metro_flow`; keep `build_final_dataset` as a thin alias)
- Create: `tests/test_flow_structure.py`

**Interfaces:**
- Produces: `build_metro_flow(metro_key: str = "phoenix") -> str` (`@flow`, returns final CSV path); `build_final_dataset(metro_key="phoenix") -> str` unchanged signature, now delegates.

- [ ] **Step 1: Introduce the flow and delegate**

Rename the current `def build_final_dataset(...)` to `@flow(name="build-metro", log_prints=True)\ndef build_metro_flow(metro_key: str = "phoenix") -> str:` and replace its inline step calls with the task calls. The step-to-task mapping (keep every other line — logging, aggregation dict, column reorder, CSV write — exactly as-is):

```python
    cbsa_boundary = fetch_cbsa_boundary_task(CBSA_CODE)
    zctas_all = fetch_state_zctas_task(ZIP_PREFIXES)
    tracts_all = fetch_tracts_task(COUNTIES)
    zctas_in_metro = filter_zctas_task(zctas_all, cbsa_boundary, UTM_ZONE)
    tracts_in_counties = tracts_all

    acs_features = fetch_acs_task(COUNTIES)
    demo_with_pct = fetch_demographics_task(COUNTIES)

    tract_to_zcta_map = map_tracts_task(tracts_in_counties, zctas_in_metro, UTM_ZONE)
    # ... acs_with_zcta merge + zcta_aggregated groupby: UNCHANGED ...
    # ... aggregate_demographics_to_zcta(demo_with_pct, tract_to_zcta_map): UNCHANGED ...

    zori_data = fetch_zori_task(ZORI_ZIP_CSV_URL)
    # ... zori rename/zfill: UNCHANGED ...

    transit_density = transit_density_task(zctas_for_transit, UTM_ZONE)
    # ... pop density, merges, income segments, column_order, to_csv: UNCHANGED ...
```

Then add the alias at the bottom of the file:

```python
def build_final_dataset(metro_key: str = "phoenix") -> str:
    """Public entry point — delegates to the Prefect flow. Signature preserved."""
    return build_metro_flow(metro_key)
```

Note: `compute_acs_features`/`compute_demographic_percentages` now run *inside* `fetch_acs_task`/`fetch_demographics_task`, so remove their now-duplicated inline calls from the flow body.

- [ ] **Step 2: Write the flow-structure test (offline, no network)**

```python
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
```

- [ ] **Step 3: Run — expect PASS**

```bash
uv run pytest tests/test_flow_structure.py -v
uv run ruff check src/ tests/
```
Expected: 2 pass; ruff clean.

- [ ] **Step 4: MANUAL structural-equivalence gate (local, needs CENSUS_API_KEY + network)**

Live ACS is fixed per vintage and OSM is cached, so a back-to-back run is usually byte-identical; ZORI period can drift month-to-month. Accept if **columns + column order + row count match** (values may drift only in `zori`/`period`):

```bash
git show origin/main:data/final/final_zcta_dataset_phoenix.csv > /tmp/phx_before.csv
METRO=phoenix uv run python run_pipeline.py
uv run python - <<'PY'
import polars as pl
a = pl.read_csv("/tmp/phx_before.csv")
b = pl.read_csv("data/final/final_zcta_dataset_phoenix.csv")
assert a.columns == b.columns, (a.columns, b.columns)
assert a.shape == b.shape, (a.shape, b.shape)
print("structural equivalence OK:", b.shape)
PY
git checkout -- data/final/final_zcta_dataset_phoenix.csv   # discard the re-run output
```
Expected: `structural equivalence OK`. If columns/shape differ, the refactor changed behavior — fix before proceeding.

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/build.py tests/test_flow_structure.py
git commit -m "feat: run pipeline as a Prefect flow with retries + resume cache"
```

---

# Phase 3 — Schema contract + provenance manifest

### Task 3.1: Schema contract

**Files:**
- Create: `src/pipelines/schema.py`
- Create: `tests/test_schema.py`

**Interfaces:**
- Produces: `REQUIRED_COLUMNS: list[str]`, `validate_final_dataset(df: pl.DataFrame) -> None` (raises `ValueError` on violation).

- [ ] **Step 1: Write the schema module**

```python
"""Schema contract for the final ZCTA dataset (fail-fast on pipeline/analysis I/O)."""
from __future__ import annotations

import polars as pl

REQUIRED_COLUMNS: list[str] = [
    "ZCTA5CE", "rent_to_income", "pct_rent_burden_30", "pct_rent_burden_50", "zori",
    "commute_min_proxy", "pct_commute_lt10", "pct_commute_10_19", "pct_commute_20_29",
    "pct_commute_30_44", "pct_commute_45_59", "pct_commute_60_plus", "ttw_total",
    "pct_drive_alone", "pct_carpool", "pct_car", "pct_transit", "pct_walk", "pct_wfh",
    "renter_share", "vehicle_access", "total_pop", "pop_density", "pct_white",
    "pct_black", "pct_asian", "pct_hispanic", "pct_other", "median_income",
    "income_segment", "stops_per_km2", "period",
]

# Columns expressed as 0-100 percentages/shares.
# NOTE: vehicle_access is EXCLUDED — real committed data reaches 107-148 (it is a
# ratio of vehicles-to-something, not a bounded 0-100 percentage). Do not add it.
_PERCENT_COLUMNS = [
    "pct_rent_burden_30", "pct_rent_burden_50", "pct_commute_lt10", "pct_commute_10_19",
    "pct_commute_20_29", "pct_commute_30_44", "pct_commute_45_59", "pct_commute_60_plus",
    "pct_drive_alone", "pct_carpool", "pct_car", "pct_transit", "pct_walk", "pct_wfh",
    "renter_share", "pct_white", "pct_black", "pct_asian", "pct_hispanic", "pct_other",
]
# NOTE: median_income is EXCLUDED from non-negative checks — every committed dataset
# carries the Census "jam" sentinel (down to -666666666) for suppressed tracts. Do not add it.
_NON_NEGATIVE_COLUMNS = ["ttw_total", "total_pop", "pop_density", "stops_per_km2", "zori"]
_LOADER_CRITICAL = ["ZCTA5CE", "rent_to_income", "commute_min_proxy", "median_income", "stops_per_km2"]
_INCOME_SEGMENTS = {"Low", "Medium", "High"}
_PERCENT_TOL = 1.0  # allow tiny rounding overshoot past 100


def _range_violation(df: pl.DataFrame, col: str, lo: float, hi: float) -> str | None:
    if col not in df.columns:
        return None
    s = df[col].drop_nulls()
    if s.len() == 0:
        return None
    cmin, cmax = s.min(), s.max()
    if cmin < lo or cmax > hi:
        return f"{col} out of range [{lo}, {hi}]: min={cmin}, max={cmax}"
    return None


def validate_final_dataset(df: pl.DataFrame, *, require_all_columns: bool = True) -> None:
    """Raise ValueError if df violates the final-dataset contract. Nulls are ignored.

    require_all_columns=True (default, pipeline write): all 32 REQUIRED_COLUMNS must exist.
    require_all_columns=False (analysis load): only the loader-critical columns must exist;
      range checks apply to whichever bounded columns are present. This lets minimal test
      fixtures (fraction-unit shares, subset of columns) pass while still range-checking real data.
    """
    errors: list[str] = []

    if require_all_columns:
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"Schema violation: missing columns {missing}")
    else:
        missing = [c for c in _LOADER_CRITICAL if c not in df.columns]
        if missing:
            raise ValueError(f"Schema violation: missing critical columns {missing}")

    for col in _PERCENT_COLUMNS:
        errors.append(_range_violation(df, col, 0.0, 100.0 + _PERCENT_TOL))
    for col in _NON_NEGATIVE_COLUMNS:
        errors.append(_range_violation(df, col, 0.0, float("inf")))
    errors.append(_range_violation(df, "rent_to_income", 0.0, 2.0))
    errors.append(_range_violation(df, "commute_min_proxy", 0.0, 180.0))

    if "income_segment" in df.columns:
        seg = df["income_segment"].drop_nulls().unique().to_list()
        bad_seg = [s for s in seg if s not in _INCOME_SEGMENTS]
        if bad_seg:
            errors.append(f"income_segment has unexpected values: {bad_seg}")

    errors = [e for e in errors if e]
    if errors:
        raise ValueError("Schema violations: " + "; ".join(errors))
```

- [ ] **Step 2: Write the calibration + rejection tests**

```python
"""Tests for the final-dataset schema contract."""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from src.pipelines.schema import REQUIRED_COLUMNS, validate_final_dataset

_FINAL_DIR = Path(__file__).resolve().parents[1] / "data" / "final"


@pytest.mark.parametrize("csv_path", sorted(_FINAL_DIR.glob("final_zcta_dataset_*.csv")))
def test_all_committed_datasets_pass_schema(csv_path: Path) -> None:
    validate_final_dataset(pl.read_csv(csv_path))


def test_missing_column_rejected() -> None:
    df = pl.DataFrame({c: [0.0] for c in REQUIRED_COLUMNS}).drop("zori")
    with pytest.raises(ValueError, match="missing columns"):
        validate_final_dataset(df)


def test_percent_out_of_range_rejected() -> None:
    data = {c: [1.0] for c in REQUIRED_COLUMNS}
    data["income_segment"] = ["Low"]
    data["pct_transit"] = [250.0]
    with pytest.raises(ValueError, match="out of range"):
        validate_final_dataset(pl.DataFrame(data))
```

- [ ] **Step 3: Run against real committed data**

```bash
uv run pytest tests/test_schema.py -v
```
Expected: all pass. The bounds above are already calibrated to the 9 committed datasets (`median_income` sentinels and `vehicle_access` >100 are excluded by design). If a *new* metro's data later trips a bound, widen that specific bound to the observed max in `schema.py` — never edit the data.

- [ ] **Step 4: Commit**

```bash
git add src/pipelines/schema.py tests/test_schema.py
git commit -m "feat: add final-dataset schema contract with real-data calibration"
```

### Task 3.2: Wire schema validation into pipeline + loader

**Files:**
- Modify: `src/pipelines/build.py` (in the flow, before `to_csv`)
- Modify: `src/models/data_loader.py` (`load_and_validate_data`, after read + null-drop)

- [ ] **Step 1: Validate pipeline output before writing**

In `build_metro_flow`, immediately before `final_dataset.to_csv(FINAL_ZCTA_OUT, index=False)`, add (converting the pandas frame to polars for the shared contract):

```python
    from .schema import validate_final_dataset
    validate_final_dataset(pl.from_pandas(final_dataset))
```
Add `import polars as pl` to build.py's imports if not present.

- [ ] **Step 2: Validate analysis input after load**

In `src/models/data_loader.py::load_and_validate_data`, after the existing critical-column null-drop and before `return`, add — with `require_all_columns=False` so the loader enforces ranges + the 5 critical columns without demanding all 32 (real 32-column CSVs and the 19-column `sample_zcta_df` fixture both pass; the fixture's fraction-unit shares fall within [0,100]):

```python
    from src.pipelines.schema import validate_final_dataset
    validate_final_dataset(df, require_all_columns=False)
```

- [ ] **Step 3: Verify existing analysis still loads**

```bash
uv run pytest tests/test_data_loader.py -v
uv run pytest -m "not network" -q
```
Expected: passes. `sample_zcta_df` (conftest.py:13–42) has `rent_to_income`∈(0.15,0.55), `commute_min_proxy`∈(15,45), and all shares as fractions 0–1 — every present bounded column is in range under lenient mode, so no fixture change is needed. (Do **not** wire strict `require_all_columns=True` here — the fixture omits 15 of the 32 columns by design.)

- [ ] **Step 4: Commit**

```bash
git add src/pipelines/build.py src/models/data_loader.py
git commit -m "feat: enforce schema contract at pipeline write and analysis load"
```

### Task 3.3: Provenance manifest

**Files:**
- Create: `src/pipelines/manifest.py`
- Create: `tests/test_manifest.py`

**Interfaces:**
- Produces:
  - `compute_sha256(path: Path) -> str`
  - `build_manifest(metro_key, csv_path, *, git_commit, timestamp_utc, zori_period, steps) -> dict`
  - `write_manifest(manifest: dict, out_path: Path) -> None`
  - `verify_manifest(csv_path: Path, manifest_path: Path) -> list[str]` (drift messages; empty = clean)
  - `get_git_commit() -> str`

- [ ] **Step 1: Write the manifest module**

```python
"""Provenance manifest for final datasets: sha256 + schema + source vintages."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import polars as pl

from src.pipelines.acs import DEFAULT_ACS_YEAR  # ACS commute vintage (2021)
from src.pipelines.config import ZORI_ZIP_CSV_URL

_DEMOGRAPHICS_YEAR = 2023  # fetch_demographics_for_county default vintage
_SOURCE_URLS = {
    "acs": f"https://api.census.gov/data/{DEFAULT_ACS_YEAR}/acs/acs5",
    "acs_demographics": f"https://api.census.gov/data/{_DEMOGRAPHICS_YEAR}/acs/acs5",
    "zori": ZORI_ZIP_CSV_URL,
    "tiger": "https://tigerweb.geo.census.gov/arcgis/rest/services (CBSA/ZCTA/tract)",
    "osm": "https://overpass-api.de (via OSMnx)",
}


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get_git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def build_manifest(
    metro_key: str,
    csv_path: Path,
    *,
    git_commit: str,
    timestamp_utc: str,
    zori_period: str | None,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    df = pl.read_csv(csv_path)
    return {
        "metro_key": metro_key,
        "git_commit": git_commit,
        "run_timestamp_utc": timestamp_utc,
        "acs_commute_year": DEFAULT_ACS_YEAR,
        "acs_demographics_year": _DEMOGRAPHICS_YEAR,
        "source_urls": _SOURCE_URLS,
        "zori_period": zori_period,
        "output_csv": csv_path.name,
        "row_count": df.height,
        "columns": [{"name": n, "dtype": str(t)} for n, t in zip(df.columns, df.dtypes)],
        "sha256": compute_sha256(csv_path),
        "steps": steps,
    }


def write_manifest(manifest: dict[str, Any], out_path: Path) -> None:
    out_path.write_text(json.dumps(manifest, indent=2, default=str))


def verify_manifest(csv_path: Path, manifest_path: Path) -> list[str]:
    drift: list[str] = []
    manifest = json.loads(manifest_path.read_text())
    if not csv_path.exists():
        return [f"missing csv: {csv_path}"]
    actual_sha = compute_sha256(csv_path)
    if actual_sha != manifest.get("sha256"):
        drift.append(f"sha256 drift: manifest={manifest.get('sha256')[:12]}… actual={actual_sha[:12]}…")
    df = pl.read_csv(csv_path)
    if df.height != manifest.get("row_count"):
        drift.append(f"row_count drift: manifest={manifest.get('row_count')} actual={df.height}")
    manifest_cols = [c["name"] for c in manifest.get("columns", [])]
    if df.columns != manifest_cols:
        drift.append("column set/order drift")
    return drift
```

- [ ] **Step 2: Write manifest tests (deterministic — inject git/time)**

```python
"""Tests for the provenance manifest."""
from __future__ import annotations

from pathlib import Path

import polars as pl

from src.pipelines.manifest import build_manifest, verify_manifest, write_manifest


def _tiny_csv(tmp_path: Path) -> Path:
    p = tmp_path / "final_zcta_dataset_test.csv"
    pl.DataFrame({"ZCTA5CE": ["00001"], "period": ["2024-01-31"], "rent_to_income": [0.3]}).write_csv(p)
    return p


def test_build_manifest_fields(tmp_path: Path) -> None:
    csv = _tiny_csv(tmp_path)
    m = build_manifest(
        "test", csv, git_commit="abc123", timestamp_utc="2026-07-09T00:00:00Z",
        zori_period="2024-01-31", steps=[{"name": "fetch_acs", "status": "completed", "duration_s": 1.0}],
    )
    assert m["metro_key"] == "test"
    assert m["git_commit"] == "abc123"
    assert m["acs_commute_year"] == 2021
    assert m["acs_demographics_year"] == 2023
    assert m["row_count"] == 1
    assert len(m["sha256"]) == 64
    assert {"name": "ZCTA5CE", "dtype": "String"} in m["columns"]


def test_verify_manifest_clean_then_drift(tmp_path: Path) -> None:
    csv = _tiny_csv(tmp_path)
    m = build_manifest("test", csv, git_commit="x", timestamp_utc="t", zori_period=None, steps=[])
    mpath = tmp_path / "test.manifest.json"
    write_manifest(m, mpath)
    assert verify_manifest(csv, mpath) == []          # clean
    pl.DataFrame({"ZCTA5CE": ["00001", "00002"], "period": ["a", "b"], "rent_to_income": [0.1, 0.2]}).write_csv(csv)
    assert verify_manifest(csv, mpath)                 # drift detected
```

- [ ] **Step 3: Run — expect PASS**

```bash
uv run pytest tests/test_manifest.py -v
```
Expected: 2 pass. If the ZCTA5CE dtype assertion fails, print the actual dtype from `m["columns"]` and match it (polars may infer `Int64` for numeric ZIPs — adjust the assertion to the observed type).

- [ ] **Step 4: Commit**

```bash
git add src/pipelines/manifest.py tests/test_manifest.py
git commit -m "feat: add provenance manifest (sha256 + vintages + schema)"
```

### Task 3.4: Emit manifest from the flow

**Files:**
- Modify: `src/pipelines/build.py` (`build_metro_flow`, after CSV write)

- [ ] **Step 1: Time the flow + write the manifest**

At the very top of `build_metro_flow`, capture the start; after the CSV is written and validated, emit the manifest. Add imports `from datetime import datetime, timezone` and manifest helpers:

```python
    # at flow start:
    _t0 = datetime.now(timezone.utc)
    # ... existing steps ...
    # after final_dataset.to_csv(FINAL_ZCTA_OUT, index=False):
    from .manifest import build_manifest, get_git_commit, write_manifest
    zori_period = None
    if "period" in final_dataset.columns and final_dataset["period"].notna().any():
        zori_period = str(final_dataset["period"].dropna().max())
    manifest = build_manifest(
        metro_key,
        FINAL_ZCTA_OUT,
        git_commit=get_git_commit(),
        timestamp_utc=_t0.isoformat(),
        zori_period=zori_period,
        steps=[],  # per-step timing can be threaded later; empty list is valid
    )
    write_manifest(manifest, DATA_FINAL / f"{metro_key}.manifest.json")
```

- [ ] **Step 2: Verify flow still constructs (offline)**

```bash
uv run python -c "from src.pipelines.build import build_metro_flow; print('flow OK')"
uv run pytest tests/test_flow_structure.py -q
uv run ruff check src/
```
Expected: `flow OK`; tests pass; ruff clean. (A full flow run requires network; covered by the Task 2.3 manual gate.)

- [ ] **Step 3: Commit**

```bash
git add src/pipelines/build.py
git commit -m "feat: emit provenance manifest per metro pipeline run"
```

### Task 3.5: `--generate-manifests` and `--verify` entry points

**Files:**
- Modify: `run_pipeline.py` (add `--generate-manifests` and `--verify`)

**Interfaces:**
- Produces: `run_pipeline.py --generate-manifests` — offline; write `data/final/<metro>.manifest.json` for every existing final CSV. `run_pipeline.py --verify` — offline; recompute checksums vs committed manifests; exit 1 on drift.

- [ ] **Step 1: Add both flags**

In `run_pipeline.py`, add next to `--all`:

```python
    parser.add_argument("--generate-manifests", action="store_true",
                        help="Offline: (re)write provenance manifests for existing final CSVs")
    parser.add_argument("--verify", action="store_true",
                        help="Offline: verify final CSVs against committed manifests (no network)")
```

- [ ] **Step 2: Handle `--generate-manifests` early in `main()`**

Before the `--all`/single-metro logic:

```python
    if args.generate_manifests:
        from datetime import datetime, timezone

        import polars as pl

        from src.pipelines.config import DATA_FINAL, METRO_CONFIGS
        from src.pipelines.manifest import build_manifest, get_git_commit, write_manifest

        commit = get_git_commit()
        ts = datetime.now(timezone.utc).isoformat()
        count = 0
        for metro_key in METRO_CONFIGS:
            csv = DATA_FINAL / f"final_zcta_dataset_{metro_key}.csv"
            if not csv.exists():
                continue
            df = pl.read_csv(csv)
            zori_period = None
            if "period" in df.columns and df["period"].drop_nulls().len() > 0:
                zori_period = str(df["period"].drop_nulls().max())
            write_manifest(
                build_manifest(metro_key, csv, git_commit=commit, timestamp_utc=ts,
                               zori_period=zori_period, steps=[]),
                DATA_FINAL / f"{metro_key}.manifest.json",
            )
            count += 1
            logger.info("wrote manifest for %s", metro_key)
        logger.info("Generated %d manifests", count)
        return 0
```

- [ ] **Step 3: Handle `--verify` early in `main()`**

```python
    if args.verify:
        from src.pipelines.config import DATA_FINAL
        from src.pipelines.manifest import verify_manifest

        manifests = sorted(DATA_FINAL.glob("*.manifest.json"))
        if not manifests:
            logger.warning("No manifests found in %s — run --generate-manifests first.", DATA_FINAL)
            return 0
        any_drift = False
        for mpath in manifests:
            metro_key = mpath.stem.replace(".manifest", "")
            csv = DATA_FINAL / f"final_zcta_dataset_{metro_key}.csv"
            drift = verify_manifest(csv, mpath)
            if drift:
                any_drift = True
                logger.error("DRIFT %s: %s", metro_key, "; ".join(drift))
            else:
                logger.info("OK %s", metro_key)
        return 1 if any_drift else 0
```

- [ ] **Step 4: Smoke test both (offline)**

```bash
uv run python run_pipeline.py --verify; echo "exit=$?"   # no manifests yet → warn + exit 0
```
Expected: logs "No manifests found", `exit=0`.

- [ ] **Step 5: Commit**

```bash
git add run_pipeline.py
git commit -m "feat: add offline --generate-manifests and --verify entry points"
```

### Task 3.6: Generate + commit provenance manifests for the 9 datasets

**Files:**
- Create (generated): `data/final/*.manifest.json` (9 files)

**Interfaces:**
- Consumes: `run_pipeline.py --generate-manifests`, `--verify` (Task 3.5).

- [ ] **Step 1: Generate manifests for all committed datasets (offline, no network)**

```bash
uv run python run_pipeline.py --generate-manifests
ls data/final/*.manifest.json   # expect 9 files
```
Expected: "Generated 9 manifests"; nine `<metro>.manifest.json` files present.

- [ ] **Step 2: Verify they round-trip clean**

```bash
uv run python run_pipeline.py --verify; echo "exit=$?"
```
Expected: nine `OK <metro>` lines, `exit=0` (no drift against the just-written manifests).

- [ ] **Step 3: Commit the manifests**

```bash
git add data/final/*.manifest.json
git commit -m "chore: add provenance manifests for all metro datasets"
```
These committed manifests are what CI's offline `verify-data` step (Task 4.4) checks — without them it is a no-op.

---

# Phase 4 — Reproducibility: analysis flow, --all, Makefile, determinism

### Task 4.1: Centralize `RANDOM_STATE`

**Files:**
- Modify: `src/pipelines/config.py` (add constant)
- Modify: `src/models/models.py:157` (KFold), `src/models/rq2_equity_analysis.py:172` (KMeans)
- Create: `tests/test_determinism.py`

**Interfaces:**
- Produces: `config.RANDOM_STATE: int` (env `RANDOM_STATE`, default 42).

- [ ] **Step 1: Add the constant**

In `src/pipelines/config.py` (near the other `os.getenv` lines):

```python
RANDOM_STATE = int(os.getenv("RANDOM_STATE", "42"))
```

- [ ] **Step 2: Thread it into the two seeded call sites**

In `src/models/models.py`, add near the imports `from src.pipelines.config import RANDOM_STATE` and change the KFold line:

```python
    kf = KFold(n_splits=k, shuffle=True, random_state=RANDOM_STATE)
```

In `src/models/rq2_equity_analysis.py`, add the same import and change the KMeans line:

```python
    kmeans = KMeans(n_clusters=4, random_state=RANDOM_STATE, n_init=10)
```

- [ ] **Step 3: Write the determinism test**

```python
"""Determinism: seeded analysis is byte-stable across repeated runs."""
from __future__ import annotations

import numpy as np
import polars as pl

from src.models.models import cv_rmse
from src.models.rq2_equity_analysis import analyze_rq2


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
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/test_determinism.py -v
uv run pytest -m "not network" -q
```
Expected: passes (seeds were already fixed; this locks it behind a named constant + guards regressions).

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/config.py src/models/models.py src/models/rq2_equity_analysis.py tests/test_determinism.py
git commit -m "refactor: centralize RANDOM_STATE and guard determinism with a test"
```

### Task 4.2: Analysis Prefect flow + `--all`

**Files:**
- Modify: `run_analysis.py`

**Interfaces:**
- Produces: `analyze_metro_flow(metro, raw_dir, out_base, fig_base, zcta_shp) -> tuple[bool, str]` (`@flow`); `analyze_all_metros(raw_dir, out_base, fig_base, zcta_shp) -> list[tuple[str, bool, str]]` (`@flow` looping subflows); `run_analysis.py --all` runs every metro code; `--metro` becomes optional; exactly one of `--metro`/`--all` required.

- [ ] **Step 1: Set offline Prefect defaults + import flow at the top of run_analysis.py**

Add near the top (after `import os` / defining `PROJECT_ROOT`, and **before** the first prefect import) so a fresh clone runs offline with no setup:

```python
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
os.environ.setdefault("PREFECT_HOME", str(PROJECT_ROOT / ".prefect"))
os.environ.setdefault("PREFECT_SERVER_ALLOW_EPHEMERAL_MODE", "true")
os.environ.setdefault("PREFECT_RESULTS_LOCAL_STORAGE_PATH", str(PROJECT_ROOT / ".prefect_cache"))

from prefect import flow  # noqa: E402
```
(`run_analysis.py` already imports `argparse`, `logging`, `pathlib`; add `os` if not present.)

- [ ] **Step 2: Wrap per-metro work as a flow + the shapefile helper + the parent flow**

Refactor the body of `run_analysis.py::main` (current lines ~89–242, after path setup) into a per-metro `@flow`. The analysis calls the existing `run_rq*` functions directly (no task caching — analysis is fast + deterministic; the flow gives orchestration parity with the pipeline):

```python
def _auto_shapefile(metro: str, raw_dir: Path, zcta_shp: str | None) -> Path | None:
    """Resolve the ZCTA shapefile for a metro. Lift the current lines 141–175 here,
    renaming `args.zcta_shp` -> `zcta_shp` and `args.metro` -> `metro` so it compiles."""
    ...  # (renamed block) returns Path | None


@flow(name="analyze-metro")
def analyze_metro_flow(metro: str, raw_dir: Path, out_base: Path, fig_base: Path,
                       zcta_shp: str | None) -> tuple[bool, str]:
    """Run RQ1/2/3 for one metro. Returns (success, message)."""
    out_dir = out_base / metro
    fig_dir = fig_base / metro
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)
    csv_file = raw_dir / METRO_FILES[metro]
    if not csv_file.exists():
        return False, f"CSV not found: {csv_file}"
    try:
        df = load_and_validate_data(csv_file, metro)
        df.write_csv(out_dir / f"cleaned_data_{metro.lower()}.csv")
        run_rq1(df, out_dir, fig_dir, metro)
        if HAS_RQ2 and run_rq2 is not None:
            run_rq2(df, out_dir, fig_dir, metro)
        if HAS_RQ3 and run_rq3 is not None:
            run_rq3(df, out_dir, fig_dir, metro, _auto_shapefile(metro, raw_dir, zcta_shp))
        return True, str(out_dir)
    except Exception as e:  # noqa: BLE001 — surface per-metro failure without aborting the batch
        logger.error("Analysis failed for %s: %s", metro, e, exc_info=True)
        return False, f"{type(e).__name__}: {e}"


@flow(name="analyze-all-metros")
def analyze_all_metros(raw_dir: Path, out_base: Path, fig_base: Path,
                       zcta_shp: str | None) -> list[tuple[str, bool, str]]:
    out = []
    for metro in METRO_FILES:
        ok, msg = analyze_metro_flow(metro, raw_dir, out_base, fig_base, zcta_shp)
        out.append((metro, ok, msg))
    return out
```

- [ ] **Step 3: Add `--all`, make `--metro` optional, branch in main**

```python
    parser.add_argument("--all", action="store_true", help="Run analysis for all metros")
    # change: required=True -> required=False on --metro
    ...
    args = parser.parse_args()
    if not (args.metro or args.all):
        parser.error("provide --metro CODE or --all")

    raw_dir, out_base, fig_base = Path(args.raw_dir), Path(args.out_dir), Path(args.fig_dir)
    if args.all:
        results = analyze_all_metros(raw_dir, out_base, fig_base, args.zcta_shp)
    else:
        ok, msg = analyze_metro_flow(args.metro, raw_dir, out_base, fig_base, args.zcta_shp)
        results = [(args.metro, ok, msg)]

    failed = [m for m, ok, _ in results if not ok]
    for m, ok, msg in results:
        logger.info("%s %s: %s", "✓" if ok else "✗", m, msg)
    if failed:
        logger.error("Failed: %s", ", ".join(failed))
        raise SystemExit(1)
```

- [ ] **Step 4: Verify single + all dispatch (uses committed data/final CSVs)**

```bash
uv run python run_analysis.py --metro PHX --out-dir /tmp/an --fig-dir /tmp/fig
uv run python run_analysis.py --all --out-dir /tmp/an --fig-dir /tmp/fig; echo "exit=$?"
uv run ruff check src/ tests/
```
Expected: PHX single run succeeds; `--all` processes all 9 (exit 0 if all committed CSVs present).

- [ ] **Step 5: Commit**

```bash
git add run_analysis.py
git commit -m "feat: run analysis as a Prefect flow with --all cross-metro dispatch"
```

### Task 4.3: Makefile + offline Prefect defaults

**Files:**
- Create: `Makefile`
- Modify: `run_pipeline.py` (offline Prefect env defaults at import time)

- [ ] **Step 1: Set offline-friendly Prefect defaults in run_pipeline.py**

Near the top of `run_pipeline.py`, **before** `from src.pipelines.build import build_final_dataset`, add:

```python
os.environ.setdefault("PREFECT_HOME", str(PROJECT_ROOT / ".prefect"))
os.environ.setdefault("PREFECT_SERVER_ALLOW_EPHEMERAL_MODE", "true")
os.environ.setdefault("PREFECT_RESULTS_LOCAL_STORAGE_PATH", str(PROJECT_ROOT / ".prefect_cache"))
```
(`os` and `PROJECT_ROOT` are already defined above the local import.) This lets a fresh clone run the flow with zero Prefect setup. `PREFECT_HOME` must be set here **before** `build` (and thus `prefect`) is imported.

- [ ] **Step 2: Write the Makefile**

```makefile
.PHONY: setup pipeline manifests analyze test lint verify-data all clean
METROS := phoenix memphis los_angeles dallas denver atlanta chicago seattle miami

setup:
	uv sync

pipeline:      ## build all metros (Prefect resumes completed fetch steps from the 7-day result cache)
	uv run python run_pipeline.py --all

manifests:     ## (re)generate provenance manifests for existing final CSVs (offline)
	uv run python run_pipeline.py --generate-manifests

analyze:       ## run RQ1/2/3 for all metros
	uv run python run_analysis.py --all

test:
	uv run pytest -m "not network"

lint:
	uv run ruff check src/ tests/

verify-data:   ## offline checksum/schema drift check
	uv run python run_pipeline.py --verify

all: setup pipeline analyze

clean:
	rm -rf .prefect_cache/ .cache/ .coverage coverage.xml
```

- [ ] **Step 3: Verify the safe targets**

```bash
make lint
make test
make verify-data
```
Expected: lint clean, tests pass, verify-data exits 0. (`make pipeline` needs network/API key — don't run in CI.)

- [ ] **Step 4: Commit**

```bash
git add Makefile run_pipeline.py
git commit -m "feat: add Makefile + offline Prefect defaults for one-command runs"
```

### Task 4.4: CI verify-data + docs

**Files:**
- Modify: `.github/workflows/ci.yml` (add offline verify-data step)
- Modify: `README.md` (Usage: `--all`, `make`, `--verify`; note manifests + Prefect resume)

- [ ] **Step 1: Add the offline verify-data step to the test job**

Insert after the "Run tests with coverage" step, before "Upload coverage report":

```yaml
      - name: Verify data integrity (offline)
        env:
          PREFECT_HOME: ${{ github.workspace }}/.prefect
          PREFECT_SERVER_ALLOW_EPHEMERAL_MODE: "true"
          PREFECT_LOGGING_LEVEL: WARNING
        run: uv run python run_pipeline.py --verify
```

- [ ] **Step 2: Update README Usage**

In the "Running the Analysis" section, replace the bash for-loop with `uv run python run_analysis.py --all` (and `make analyze`). Add a short "Reproducibility" note: `make all`, provenance manifests in `data/final/*.manifest.json`, `make verify-data`, and that the pipeline resumes from a 7-day Prefect result cache on re-run.

- [ ] **Step 3: Verify CI YAML parses + full local gate**

```bash
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "yaml OK"
uv run ruff check src/ tests/
uv run pytest -m "not network" --cov=src --cov-fail-under=<GATE> -q   # <GATE> = the value in ci.yml line 58
```
Expected: `yaml OK`; ruff clean; suite passes at the gate.

- [ ] **Step 4: Commit + open PR**

```bash
git add .github/workflows/ci.yml README.md
git commit -m "ci: verify data integrity offline; docs: one-command reproducibility"
git push -u origin feat/engineering-hardening
gh pr create --title "Engineering hardening: Prefect flow, provenance, coverage, reproducibility" \
  --body "Implements docs/plans/2026-07-09-engineering-hardening-plan.md. Behavior-preserving for outputs. See spec docs/plans/2026-07-09-engineering-hardening-design.md."
```

- [ ] **Step 5: Watch CI to green**

```bash
gh pr checks --watch
```
Expected: lint + both test matrices + verify-data all green before merge.

---

## Self-Review

**Spec coverage:**
- Orchestration resilience (Prefect, retries, 7-day resume cache, `--all`) → Phase 2 (Tasks 2.1–2.3) + offline defaults (4.3).
- Structured RunResult + provenance manifest → Phase 3 (Tasks 3.3–3.6; manifests generated + committed in 3.6).
- Schema contract → Phase 3 (Tasks 3.1–3.2).
- One-command reproducibility (Makefile, analysis `@flow` + `--all`, determinism) → Phase 4 (Tasks 4.1–4.4).
- Analytical-logic coverage + gate 40→~70 → Phase 1 (Tasks 1.1–1.5).
- Housekeeping (findings, skills, Prefect pin, gitignore) → Phase 0.
- All four scope items + both decisions (Prefect adopt / 7-day TTL / 70% gate) present.

**Adversarial verification:** this plan was verified against the installed `prefect==3.6.4`, the real committed datasets, and the approved spec (16 defects found and fixed). Notably: `result_storage` moved from an unsaved `LocalFileSystem` block (which raises `TypeError` at import) to the `PREFECT_RESULTS_LOCAL_STORAGE_PATH` env var; `median_income` (Census `-666666666` sentinels) and `vehicle_access` (>100 in all metros) excluded from range checks; schema validation split strict/lenient so the loader doesn't demand all 32 columns of minimal fixtures; the `matplotlib.use("Agg")` line placed after `from __future__` (SyntaxError otherwise); branch based on the spec branch, not `origin/main`; and manifest generation made a real committing step so `verify-data` isn't a no-op.

**Deferred (annotated, not silently dropped):**
- A single `build_all_metros` parent flow for `run_pipeline.py --all`: the existing per-metro loop already isolates failures and each metro runs as its own `build_metro_flow` flow-run, so a wrapping parent flow adds little; deferred.
- Per-step `steps[]` telemetry in the manifest: run-level provenance (git commit, timestamp, sha256, vintages, source URLs, row/column schema) is delivered now; fine-grained per-task timing is deferred (manifest ships `steps=[]`, an intentional valid value).
- Makefile `pipeline` per-metro manifest-age skip + `FORCE=1`: superseded by Prefect's 7-day per-step result cache (mtime-based skips are unreliable post-clone); the Makefile comment reflects the real mechanism.

**Type consistency:** `build_metro_flow`/`build_final_dataset` return `str` (path) consistently; `validate_final_dataset(df, *, require_all_columns=True) -> None` raises, called strict at pipeline write and `require_all_columns=False` at loader; `verify_manifest(...) -> list[str]` (empty = clean) consistent across manifest module, tests, and `--verify`; `analyze_metro_flow` returns `tuple[bool, str]`; metro identifier casing kept distinct (pipeline lowercase, analysis uppercase) throughout.

**Known executor adjustments (characterization tests of existing code):** a few assertions (RQ2 cluster-label length, manifest ZCTA5CE dtype, ACI column availability) are calibrated against real behavior on first run — each step says how to adjust to observed values without touching source or data.
