# RQ4: ZORI Rent Dynamics Implementation Plan

> **For agentic workers:** Execute this plan task-by-task (one agent per task where convenient); steps use checkbox (`- [ ]`) syntax for tracking. Read `docs/plans/2026-07-17-rq4-zori-dynamics-design.md` (rev 2) before starting any task — every design reference below (§1–§6) points into it.

**Goal:** Add RQ4 — did COVID reprice the commute gradient? — from the ZORI monthly ZIP panel (smoothed non-SA, 2015–present) plus annual LODES8 job accessibility (2015–2023) and a pre-COVID ACS 2019 commute vintage, per `docs/plans/2026-07-17-rq4-zori-dynamics-design.md`.

**Architecture:** Three new per-metro committed data products (`zori_panel_*.csv`, `lodes_panel_*.csv`, `acs_commute_2019_*.csv`) built by a new separate Prefect flow `src/pipelines/panel.py::build_panel_flow` (`run_pipeline.py --panel`), gated by a new `scripts/panel_gate.py` (snapshot-replace + revision report for ZORI; append-only int-byte/float-rtol for LODES/ACS), and consumed by a new `src/models/rq4_rent_dynamics.py` (two-way FE within estimator + Webb wild cluster bootstrap in `src/models/panel_fe.py`). The cross-sectional path — `build_metro_flow`, 35-column schema, `rebuild_gate.py`, committed `final_zcta_dataset_*.csv` — is untouched.

**Tech Stack:** Python 3.11+, pandas/geopandas/polars/numpy/statsmodels, Prefect 3 (local-only), pytest, uv.

## Global Constraints

- Run all tests with `uv run pytest` from the repo root. Lint with `uv run ruff check src/ tests/`.
- Commit messages: conventional style (`feat:`, `fix:`, `test:`, `docs:`, `chore:`). **No Co-Authored-By or agent-attribution lines.**
- All ZCTA join keys are `str` zero-padded to 5 digits. Polars reads of panel CSVs use `schema_overrides={"ZCTA5CE": pl.Utf8}`; pandas reads in the gate use `dtype=str` (+ `pd.to_numeric` for tolerance checks) — design §1 "Dtype round-trip conventions".
- Prefect cacheable tasks use `**NETWORK_RETRIES, **_CACHE` (`INPUTS + TASK_SOURCE`, 7-day TTL, `persist_result=True`); inputs to cacheable tasks must be hashable (tuples/str/int — never DataFrames). Do NOT add `pyarrow`. Do NOT set `result_storage` on tasks.
- New constants (defined once, imported everywhere): `ZORI_PANEL_CSV_URL` (config.py, smoothed non-SA), `LODES_PANEL_YEARS = tuple(range(2015, 2024))` (lodes.py), `TTW_MIDPOINTS` (acs.py), `ENDPOINT_TRIM_MONTHS = 1`, `POST1_START/POST1_END/POST2_START` (rq4 module), gate tolerance constants (panel_gate.py).
- **Cache-safety invariants:** `fetch_zori_task` and `fetch_lodes_task` bodies in `build.py` must not change (their `TASK_SOURCE` keys must survive). While iterating on panel helper code under a warm cache, clear `.prefect_cache/` or bump `_PANEL_CACHE_SALT` (design §2 dev-loop note).
- Tasks marked **[NETWORK]** need live internet (Tasks 7, 13, 21 partially; Task 13 also needs `CENSUS_API_KEY` in `.env`). Everything else is offline with monkeypatched HTTP.
- Stable-sort before every aggregation/write that feeds committed bytes (issue #6 convention).
- Phase 1 Task 7 and Phase 2 Task 13 commit data; each phase's data + code land in the same PR so committed manifests never reference untracked or absent CSVs.

## File Structure

```
Create:
  src/pipelines/panel.py               # build_panel_flow + panel tasks (separate from build_metro_flow)
  src/models/panel_fe.py               # within-FE estimator + Webb wild cluster bootstrap (pure, reusable)
  src/models/rq4_rent_dynamics.py      # analyze/report/run for RQ4
  scripts/panel_gate.py                # ZORI snapshot gate + LODES/ACS append-only gate
  tests/test_panel_pipeline.py         # tidy_zori, fetch_zori_series, lodes panel, acs vintage (offline)
  tests/test_panel_gate.py             # gate FAIL/PASS matrix
  tests/test_panel_fe.py               # LSDV equality (coef+SE), recovery, bootstrap
  tests/test_rq4.py                    # analyze/report/results tests
  tests/fixtures/zori_wide_fixture.csv           # synthetic Zillow wide CSV
  tests/fixtures/zori_latest_golden.csv          # golden output generated from PRE-refactor code
Modify:
  .gitignore                           # 3 negations for the new data products
  src/pipelines/config.py              # ZORI_PANEL_CSV_URL
  src/pipelines/zori.py                # extract tidy_zori; add fetch_zori_series
  src/pipelines/lodes.py               # fetch_state_xwalk, fetch_state_lodes_panel, job_accessibility_by_year, LODES_PANEL_YEARS
  src/pipelines/acs.py                 # TTW_MIDPOINTS extraction; fetch_acs_commute_zcta
  src/pipelines/schema.py              # validate_zori_panel / validate_lodes_panel / validate_acs_commute_2019 (additive)
  src/pipelines/manifest.py            # build_panel_manifest (years-parameterized provenance)
  run_pipeline.py                      # --panel flag; --verify pairs manifests via output_csv
  Makefile                             # panel: target
  src/models/results.py                # frozen RQ4Results
  src/models/data_loader.py            # PANEL_FILES + load_panel_data
  run_analysis.py                      # HAS_RQ4 optional-import wiring + skip-when-absent
  tests/test_flow_structure.py         # new cacheable tasks in cache-key + TASK_SOURCE tests
  tests/test_manifest.py               # panel manifest + tracked-file assertions
  tests/test_schema.py                 # panel validator tests (additive)
  tests/conftest.py                    # synthetic panel fixtures for RQ4 tests
  data/final/zori_panel_*.csv (+9 manifests)            # Task 7  [NETWORK]
  data/final/lodes_panel_*.csv, acs_commute_2019_*.csv (+18 manifests)  # Task 13  [NETWORK]
  docs/findings.md, README.md, RUNNING_PIPELINE.md, src/pipelines/PIPELINE_README.md  # Phase 4
```

---

# Phase 1 — ZORI panel pipeline + gate

### Task 1: Golden fixture, then `tidy_zori` extraction (byte-identical `fetch_zori_latest`)  [offline]

**Files:**
- Create: `tests/fixtures/zori_wide_fixture.csv`, `tests/fixtures/zori_latest_golden.csv`, `tests/test_panel_pipeline.py`
- Modify: `src/pipelines/zori.py`

**Interfaces:**
- Produces: `tidy_zori(wide_df: pd.DataFrame) -> pd.DataFrame[zip, period, zori]` (module-level helper); `fetch_zori_latest` re-expressed as `tidy_zori(...) + tail(1)` with byte-identical output. **Order matters: the golden fixture is generated from the PRE-refactor code, or the equality test proves nothing (design §Verification 1).**

- [ ] **Step 1: Generate fixtures from the CURRENT (pre-refactor) code**

Create `tests/fixtures/zori_wide_fixture.csv` — a synthetic Zillow-shaped wide CSV: columns `RegionID,SizeRank,RegionName,RegionType,StateName,State,City,Metro,CountyName,2015-01-31,2015-02-28,2020-03-31,2026-06-30`, ~8 rows spanning: a ZIP with full history, a ZIP with leading zero (`501`), a ZIP with `MA` non-numeric cells, a ZIP with a missing tail month, ZIPs matching prefixes `850`/`851` and one non-matching (`38103`). Then generate the golden:

```bash
uv run python - <<'EOF'
import pandas as pd
from src.pipelines import zori
wide = pd.read_csv("tests/fixtures/zori_wide_fixture.csv")
import src.pipelines.utils as utils
# bypass HTTP: call the internals by monkeypatching http_csv_to_df
zori.http_csv_to_df = lambda url: wide.copy()
zori.fetch_zori_latest("fixture://").to_csv("tests/fixtures/zori_latest_golden.csv", index=False)
EOF
git add tests/fixtures/ && git commit -m "test: golden ZORI latest fixture from pre-refactor tidy logic"
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_panel_pipeline.py`:

```python
"""Offline tests for the RQ4 panel pipeline (monkeypatched HTTP throughout)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import src.pipelines.zori as zori

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def zori_wide() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "zori_wide_fixture.csv")


def _patch_http(monkeypatch, wide: pd.DataFrame) -> None:
    monkeypatch.setattr(zori, "http_csv_to_df", lambda url: wide.copy())


def test_tidy_zori_long_shape(zori_wide) -> None:
    out = zori.tidy_zori(zori_wide)
    assert list(out.columns) == ["zip", "period", "zori"]
    assert out["zip"].str.len().eq(5).all()          # zero-padded
    assert out["zori"].notna().all()                  # MA + NaN cells dropped
    assert not out.duplicated(["zip", "period"]).any()


def test_fetch_zori_latest_byte_identical_to_golden(monkeypatch, zori_wide) -> None:
    """The tidy_zori refactor must not change fetch_zori_latest by one byte —
    fetch_zori_task's TASK_SOURCE cache key survives only because build.py's
    wrapper body is untouched; this pins the *output* too."""
    _patch_http(monkeypatch, zori_wide)
    got = zori.fetch_zori_latest("fixture://").to_csv(index=False)
    golden = (FIXTURES / "zori_latest_golden.csv").read_text()
    assert got == golden


def test_tidy_zori_tail_equals_latest(monkeypatch, zori_wide) -> None:
    """Same-pull consistency: last row per zip of the tidy frame == latest frame."""
    _patch_http(monkeypatch, zori_wide)
    latest = zori.fetch_zori_latest("fixture://").reset_index(drop=True)
    tail = (
        zori.tidy_zori(zori_wide)
        .sort_values(["zip", "period"]).groupby("zip", as_index=False).tail(1)
        [["zip", "period", "zori"]].reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(tail, latest)
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_panel_pipeline.py -v`
Expected: FAIL with `AttributeError: module 'src.pipelines.zori' has no attribute 'tidy_zori'`.

- [ ] **Step 4: Implement**

In `src/pipelines/zori.py`, move the body of `fetch_zori_latest` between the rename and the `dropna` (lines ~41–77: rename → zfill → date-col detection → melt → dropna → to_numeric → dropna) into:

```python
def tidy_zori(zori_data: pd.DataFrame) -> pd.DataFrame:
    """Zillow wide CSV -> long [zip, period, zori]; drops non-numeric/missing cells.

    Extracted verbatim from fetch_zori_latest so the latest-month path stays
    byte-identical (proven against tests/fixtures/zori_latest_golden.csv).
    """
```

then `fetch_zori_latest(url)` becomes: `http_csv_to_df(url)` → `tidy_zori(...)` → the existing sort/groupby/tail/astype/select, **in the same operation order** (keep the debug-logging block inside `tidy_zori` where the melt lives).

- [ ] **Step 5: Run to verify green + full-suite regression**

Run: `uv run pytest tests/test_panel_pipeline.py tests/test_flow_structure.py -v && uv run pytest -q`
Expected: all PASS (byte-equality proves the refactor is invisible; nothing else touched).

- [ ] **Step 6: Commit**

```bash
git add src/pipelines/zori.py tests/test_panel_pipeline.py
git commit -m "refactor(pipeline): extract tidy_zori; fetch_zori_latest byte-identical (golden-pinned)"
```

---

### Task 2: `ZORI_PANEL_CSV_URL` + `fetch_zori_series`  [offline]

**Files:**
- Modify: `src/pipelines/config.py` (beside `ZORI_ZIP_CSV_URL`, `config.py:172`), `src/pipelines/zori.py`
- Test: `tests/test_panel_pipeline.py`

**Interfaces:**
- Produces: `ZORI_PANEL_CSV_URL = "https://files.zillowstatic.com/research/public_csvs/zori/Zip_zori_uc_sfrcondomfr_sm_month.csv"` (smoothed **non-SA** — design §4 "Index choice"; verified live 2026-07-17, ~9.8 MB); `fetch_zori_series(url, zip_prefixes: tuple[str, ...]) -> pd.DataFrame[zip, period, zori]` — tidy + prefix filter, stable-sorted by `(zip, period)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_panel_pipeline.py`:

```python
def test_fetch_zori_series_prefix_filter(monkeypatch, zori_wide) -> None:
    _patch_http(monkeypatch, zori_wide)
    out = zori.fetch_zori_series("fixture://", ("850", "851"))
    assert set(out.columns) == {"zip", "period", "zori"}
    assert out["zip"].str[:3].isin({"850", "851"}).all()
    assert "38103" not in set(out["zip"])            # non-matching ZIP excluded
    # stable-sorted for deterministic committed bytes (issue #6 convention)
    assert out.equals(out.sort_values(["zip", "period"], kind="stable", ignore_index=True))


def test_zori_panel_url_is_non_sa() -> None:
    from src.pipelines.config import ZORI_PANEL_CSV_URL, ZORI_ZIP_CSV_URL
    assert ZORI_PANEL_CSV_URL.endswith("_sm_month.csv")        # no _sa_
    assert ZORI_ZIP_CSV_URL.endswith("_sm_sa_month.csv")       # cross-sectional untouched
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_panel_pipeline.py -v`; expected `AttributeError` / `ImportError`.

- [ ] **Step 3: Implement** — add the constant with a provenance comment (SA look-ahead rationale, one line pointing at design §4); implement `fetch_zori_series` as `tidy_zori(http_csv_to_df(url))` + `zip.str[:3].isin(prefixes)`-style startswith filter (use `str.startswith(tuple(...))` to support non-3-char prefixes) + stable sort + `reset_index(drop=True)`.

- [ ] **Step 4: Run to verify green** — `uv run pytest tests/test_panel_pipeline.py -v`.

- [ ] **Step 5: Commit** — `git commit -m "feat(pipeline): fetch_zori_series over the non-SA ZORI panel URL"`

---

### Task 3: `validate_zori_panel` schema validator  [offline]

**Files:**
- Modify: `src/pipelines/schema.py` (additive; `REQUIRED_COLUMNS`/`validate_final_dataset` untouched)
- Test: `tests/test_schema.py` (append)

**Interfaces:**
- Produces: `validate_zori_panel(df: pl.DataFrame) -> list[str]` — empty list = valid. Checks (design §1/§5): exact columns `[ZCTA5CE, period, zori]`; `ZCTA5CE` is Utf8, 5-digit; `period` ISO month-end date string; `zori > 0` and **non-null** (the "absent rows, never nulls" invariant, enforced); no duplicate `(ZCTA5CE, period)` keys.

- [ ] **Step 1: Failing tests** — append to `tests/test_schema.py`: a valid 3-row frame passes; each violation (null zori, zori ≤ 0, dup key, bad date `2020-13-99`, i64 ZCTA5CE) returns a non-empty error list naming the check.
- [ ] **Step 2: Run** — expected `ImportError: cannot import name 'validate_zori_panel'`.
- [ ] **Step 3: Implement** — mirror `validate_final_dataset`'s error-list style; date check via `pl.col("period").str.to_date("%Y-%m-%d", strict=False).is_null()`.
- [ ] **Step 4: Run green**, then full `uv run pytest tests/test_schema.py -q` (existing tests untouched).
- [ ] **Step 5: Commit** — `git commit -m "feat(schema): zori panel validator (additive)"`

---

### Task 4: `panel.py` flow (ZORI half) + `--panel` CLI  [offline]

**Files:**
- Create: `src/pipelines/panel.py`
- Modify: `run_pipeline.py` (new flag beside `run_pipeline.py:143-151`), `Makefile`
- Test: `tests/test_flow_structure.py`, `tests/test_panel_pipeline.py`

**Interfaces:**
- Produces: `build_panel_flow(metro_key)` Prefect flow; `fetch_zori_series_task(url, zip_prefixes)` (cacheable: `**NETWORK_RETRIES, **_CACHE`); `zori_panel_task(zori_long, zctas_in_metro)` (plain `@task`: rename `zip`→`ZCTA5CE`, inner-filter to the metro ZCTA set, stable-sort, return); flow writes `data/final/zori_panel_<metro>.csv` after `validate_zori_panel` (raise on errors). Reuses `fetch_cbsa_boundary_task`/`fetch_state_zctas_task`/`filter_zctas_task` imported from `build.py` (cache shared — flow-agnostic keys). Module docstring carries the **dev-loop cache note** and `_PANEL_CACHE_SALT` (design §2). LODES/ACS halves land in Phase 2.
- CLI: `run_pipeline.py --panel` (with `--all` composing) runs `build_panel_flow` instead of `build_metro_flow`; no-flag behavior unchanged. `Makefile`: `panel:` target.

- [ ] **Step 1: Failing tests** — extend `tests/test_flow_structure.py`: add `fetch_zori_series_task` to the distinct-cache-key test (same-inputs key must differ from `fetch_zori_task`'s: inputs `{"url": "x", "zip_prefixes": ("850",)}` vs `{"url": "x"}` — assert TASK_SOURCE component present per the existing `test_cacheable_tasks_include_task_source_component` pattern) and `test_build_panel_flow_is_a_flow`. In `tests/test_panel_pipeline.py`: `zori_panel_task.fn(...)` unit test (rename/filter/sort on synthetic frames — call `.fn` to bypass the runner, matching existing test style).
- [ ] **Step 2: Run** — expected `ImportError` on `src.pipelines.panel`.
- [ ] **Step 3: Implement** — flow body: config reads → shared geo tasks → `fetch_zori_series_task(ZORI_PANEL_CSV_URL, tuple(ZIP_PREFIXES))` → `zori_panel_task` → validate → write CSV. No `result_storage`; no pyarrow. Wire the CLI flag and Makefile target.
- [ ] **Step 4: Run green** — `uv run pytest tests/test_flow_structure.py tests/test_panel_pipeline.py -v`.
- [ ] **Step 5: Commit** — `git commit -m "feat(pipeline): build_panel_flow (ZORI half) + run_pipeline --panel"`

---

### Task 5: Panel manifests, `.gitignore` negations, `--verify` pairing fix  [offline]

**Files:**
- Modify: `.gitignore` (after line 47), `src/pipelines/manifest.py`, `run_pipeline.py:170-172`, `src/pipelines/panel.py`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Produces: `build_panel_manifest(metro_key, csv_path, kind, *, git_commit, timestamp_utc, extra: dict) -> dict` in `manifest.py` — reuses `compute_sha256`/`_metro_config_snapshot`/provenance modes/`cbsa_vintage`, but **parameterizes sources per kind** (design §3 Manifests): `kind="zori_panel"` → source = `ZORI_PANEL_CSV_URL` + `pull_timestamp_utc`, `period_min/max`, `n_months`, `n_zctas`; `kind="lodes_panel"` → lodes URL pattern + explicit `years` list (never the `_SOURCE_URLS` string interpolating `LODES_YEAR=2021`); `kind="acs_commute_2019"` → ACS 2019 vintage. `verify_manifest` reused as-is.
- `.gitignore` gains: `!data/final/zori_panel_*.csv`, `!data/final/lodes_panel_*.csv`, `!data/final/acs_commute_2019_*.csv`.
- `--verify` resolves each manifest's CSV from `manifest["output_csv"]` (already written at `manifest.py:111`), falling back to the `final_zcta_dataset_{stem}.csv` convention when the field is absent.

- [ ] **Step 1: Failing tests** — append to `tests/test_manifest.py`:

```python
def test_panel_manifest_lodes_provenance_uses_years_not_2021(tmp_path) -> None:
    import polars as pl
    from src.pipelines.manifest import build_panel_manifest

    csv = tmp_path / "lodes_panel_test.csv"
    pl.DataFrame({"ZCTA5CE": ["85001"], "year": [2015]}).write_csv(csv)
    m = build_panel_manifest(
        "test", csv, "lodes_panel",
        git_commit="abc", timestamp_utc="2026-01-01T00:00:00+00:00",
        extra={"years": list(range(2015, 2024))},
    )
    assert m["years"] == list(range(2015, 2024))
    assert "2021" not in m["source_urls"]["lodes"]          # no stale single-year stamp
    assert m["output_csv"] == "lodes_panel_test.csv"


def test_committed_manifests_reference_tracked_csvs() -> None:
    """A manifest must never land while its CSV is gitignored (design §1)."""
    import json
    import subprocess
    from src.pipelines.config import DATA_FINAL

    for mpath in sorted(DATA_FINAL.glob("*.manifest.json")):
        out_csv = json.loads(mpath.read_text()).get("output_csv")
        if out_csv is None:
            continue
        rc = subprocess.run(
            ["git", "check-ignore", "-q", str(DATA_FINAL / out_csv)],
            cwd=DATA_FINAL.parent.parent,
        ).returncode
        assert rc != 0, f"{mpath.name} references gitignored CSV {out_csv}"
```

Plus a `--verify` pairing test: write a fake `x.zori_panel.manifest.json` + matching `zori_panel_x.csv` into a tmp DATA_FINAL (monkeypatched) and assert verify pairs them via `output_csv` (import the verify helper after extracting it into a function if needed).

- [ ] **Step 2: Run** — expected `ImportError` on `build_panel_manifest`; the tracked-CSV test passes vacuously (no panel manifests yet) — keep it as the standing guard.
- [ ] **Step 3: Implement** — manifest builder + gitignore lines + the `--verify` edit (extract the loop body into a small pairing helper so it is testable). Panel flow calls `build_panel_manifest` after writing each CSV.
- [ ] **Step 4: Run green** — `uv run pytest tests/test_manifest.py -v && uv run pytest -q`.
- [ ] **Step 5: Commit** — `git commit -m "feat(pipeline): panel manifests with vintage provenance; gitignore negations; --verify pairs via output_csv"`

---

### Task 6: `scripts/panel_gate.py` — ZORI structural + revision checks  [offline]

**Files:**
- Create: `scripts/panel_gate.py`, `tests/test_panel_gate.py`

**Interfaces:**
- Produces: `python scripts/panel_gate.py <baseline_dir> [--accept-revisions] [--accept-structural] [--accept-access-drift]`, exit 0/1. Named constants at top: `ZCTA_CHURN_MAX = 0.05`, `LOST_CELLS_MAX = 0.01`, `REVISED_CELLS_MAX = 0.01`, `REVISION_TOL = 0.05`, `REVISION_MAX_SINGLE = 0.25`, `FLOAT_NOISE_RTOL = 1e-12` (same value as `rebuild_gate.py:47-49`). ZORI checks per design §3 with **explicit denominators**: churn over baseline ZCTAs; lost-cells over baseline cells of the **intersection** ZCTA set. Revision report: count/median/p99/max of |Δ|/baseline over overlapping cells. `--accept-structural` waives checks 2–4 (never schema check 1) and prints exactly what it waived; `--accept-revisions` waives the tolerance check only. Reads with `dtype=str`, numeric compares via `pd.to_numeric` (design §1). LODES/ACS sections stubbed with a clear "Phase 2" marker (Task 12 fills them).

- [ ] **Step 1: Failing tests** — `tests/test_panel_gate.py`, driving the gate's `check_zori_panel(baseline_df, new_df) -> GateResult` function directly (no subprocess), covering each cell of the FAIL/PASS matrix:

```python
"""Gate matrix for panel_gate.py (offline; frames built inline)."""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.panel_gate import check_zori_panel


def _panel(cells: list[tuple[str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(cells, columns=["ZCTA5CE", "period", "zori"])


BASE = _panel([
    ("85001", "2020-01-31", 1500.0), ("85001", "2020-02-29", 1510.0),
    ("85002", "2020-01-31", 1200.0), ("85002", "2020-02-29", 1210.0),
])


def test_identical_passes() -> None:
    assert check_zori_panel(BASE, BASE.copy()).ok


def test_lost_month_fails() -> None:
    new = BASE[BASE["period"] != "2020-02-29"]
    r = check_zori_panel(BASE, new)
    assert not r.ok and any("month" in e for e in r.errors)


def test_small_revision_passes_with_report() -> None:
    new = BASE.copy()
    new.loc[0, "zori"] *= 1.001                      # 0.1% « 5% tolerance
    r = check_zori_panel(BASE, new)
    assert r.ok and r.revision_report["n_revised"] == 1


def test_single_cell_over_25pct_fails() -> None:
    new = BASE.copy()
    new.loc[0, "zori"] *= 1.30
    assert not check_zori_panel(BASE, new).ok


def test_churned_zcta_cells_do_not_count_as_lost_cells() -> None:
    """Design §3 check 4: lost-cells over the INTERSECTION ZCTA set only —
    churn that check 3 permits must not mechanically trip check 4."""
    new = BASE[BASE["ZCTA5CE"] != "85002"]           # 50% churn: fails check 3...
    r = check_zori_panel(BASE, new)
    assert any("churn" in e for e in r.errors)
    assert not any("lost cells" in e for e in r.errors)   # ...but NOT check 4


def test_accept_structural_waives_churn_not_schema() -> None:
    new = BASE[BASE["ZCTA5CE"] != "85002"]
    assert check_zori_panel(BASE, new, accept_structural=True).ok
    bad = BASE.copy(); bad["zori"] = -1.0            # schema: no bypass, ever
    assert not check_zori_panel(BASE, bad, accept_structural=True).ok
```

(Also: duplicate-key FAIL; >1%-of-cells-revised-over-5% FAIL then `accept_revisions=True` PASS.)

- [ ] **Step 2: Run** — expected `ModuleNotFoundError: scripts.panel_gate` (add `scripts/__init__.py` if the existing `test_rebuild_gate.py` import pattern requires it — mirror whatever it does).
- [ ] **Step 3: Implement** — `GateResult` dataclass (`ok`, `errors`, `revision_report`); `check_zori_panel` + a `main()` that loads baseline/new per metro, prints the report, applies accept flags, returns exit code. Docstring states denominators and the review-only contract for the flags (PR must quote gate output).
- [ ] **Step 4: Run green** — `uv run pytest tests/test_panel_gate.py -v`.
- [ ] **Step 5: Commit** — `git commit -m "feat(gate): panel_gate with ZORI snapshot-replace checks + reviewed escape hatches"`

---

### Task 7: Live ZORI panel build ×9, calibration double-build, commit data  [NETWORK]

**Files:**
- Modify: `data/final/zori_panel_*.csv` ×9 + `*.zori_panel.manifest.json` ×9 (new)

- [ ] **Step 1: Phoenix first**

```bash
METRO=phoenix uv run python run_pipeline.py --panel
```

Expected: `data/final/zori_panel_phoenix.csv` (~13.3k rows per the design coverage table ±Zillow drift since 2026-07-17) + manifest with `pull_timestamp_utc`, `period_min=2015-01-31`. Sanity: `uv run python -c "import polars as pl; df = pl.read_csv('data/final/zori_panel_phoenix.csv', schema_overrides={'ZCTA5CE': pl.Utf8}); print(df.shape, df['period'].min(), df['period'].max())"`.

- [ ] **Step 2: Calibration double-build** — snapshot the phoenix CSV to the scratch dir, clear only the zori cache entry (or wait for a same-day re-run: same vintage), rebuild, run the gate:

```bash
uv run python scripts/panel_gate.py /path/to/snapshot_dir
```

Expected: structural PASS, revisions = 0 (same-day vintage). Record the output — this is the first tolerance-calibration datapoint (design §3). If Zillow published between runs, expect small tail revisions; verify they sit ≪ the 5% tolerance and note the observed p99 in the PR body.

- [ ] **Step 3: All nine** — `uv run python run_pipeline.py --panel --all`; then `uv run python run_pipeline.py --verify` (expected: OK ×18 — 9 cross-sectional + 9 zori-panel, correctly paired via `output_csv`); then full `uv run pytest -q` (the tracked-CSV manifest test now runs non-vacuously).
- [ ] **Step 4: Verify coverage against the design table** — row counts within ~2% of the §Data-availability table (non-SA vs SA coverage check the design promises); investigate any metro off by more.
- [ ] **Step 5: Commit + Phase-1 PR**

```bash
git add .gitignore data/final/zori_panel_*.csv data/final/*.zori_panel.manifest.json
git commit -m "feat(data): commit ZORI monthly panels x9 (non-SA vintage) behind panel gate"
git push -u origin feat/rq4-zori-dynamics
gh pr create --title "RQ4 phase 1: ZORI panel pipeline + gate" --body "<summary + gate output + calibration numbers>"
```

Run the repo CI gate locally before pushing; watch checks go green.

---

# Phase 2 — LODES annual accessibility panel + pre-COVID ACS vintage

### Task 8: `fetch_state_xwalk` + `fetch_state_lodes_panel`  [offline]

**Files:**
- Modify: `src/pipelines/lodes.py`
- Test: `tests/test_lodes.py` (append)

**Interfaces:**
- Produces: `LODES_PANEL_YEARS = tuple(range(2015, 2024))`; `fetch_state_xwalk(state_postal) -> pd.DataFrame` (extracted from `fetch_state_jobs`, which now calls it — existing outputs unchanged); `fetch_state_lodes_panel(state_postal, years: tuple) -> pd.DataFrame[year, zcta, trct, jobs]` — downloads the xwalk **once**, loops the years' WACs; an HTTP error on any year **propagates** (no silent zero-fill; design §2). Also fix the stale `lodes.py:79` docstring ("10–60 MB gz" → "2.7–11.4 MB gz, verified 2026-07-17").

- [ ] **Step 1: Failing tests** — append to `tests/test_lodes.py` (reusing its `_fake_http` fixture style):

```python
def test_fetch_state_lodes_panel_one_xwalk_fetch(monkeypatch) -> None:
    calls = {"xwalk": 0, "wac": 0}
    def fake(url: str, timeout: int = 180, **kwargs):
        if "/wac/" in url:
            calls["wac"] += 1
            return pd.DataFrame({"w_geocode": ["1" * 15], "C000": [4]})
        calls["xwalk"] += 1
        return pd.DataFrame({"tabblk2020": ["1" * 15], "zcta": ["38103"], "trct": ["1" * 11]})
    monkeypatch.setattr(lodes, "http_csv_to_df", fake)
    out = lodes.fetch_state_lodes_panel("tn", (2015, 2016, 2017))
    assert calls == {"xwalk": 1, "wac": 3}           # xwalk once, one WAC per year
    assert set(out["year"]) == {2015, 2016, 2017}
    assert list(out.columns) == ["year", "zcta", "trct", "jobs"]


def test_fetch_state_lodes_panel_404_year_raises(monkeypatch) -> None:
    """A missing state-year must be a loud failure, never a zero-fill (design §2)."""
    import requests
    def fake(url: str, timeout: int = 180, **kwargs):
        if "_2016.csv.gz" in url:
            raise requests.HTTPError("404 Not Found")
        if "/wac/" in url:
            return pd.DataFrame({"w_geocode": ["1" * 15], "C000": [4]})
        return pd.DataFrame({"tabblk2020": ["1" * 15], "zcta": ["38103"], "trct": ["1" * 11]})
    monkeypatch.setattr(lodes, "http_csv_to_df", fake)
    with pytest.raises(requests.HTTPError):
        lodes.fetch_state_lodes_panel("tn", (2015, 2016))


def test_fetch_state_jobs_unchanged_via_xwalk_helper(monkeypatch) -> None:
    """The extraction must leave the single-year path's output identical."""
    # reuse the existing test_fetch_state_jobs_aggregates_and_drops_unassigned
    # fixtures; assert same output frame as before the refactor.
```

- [ ] **Step 2: Run** — expected `AttributeError` on the two new functions.
- [ ] **Step 3: Implement** — extraction + per-year loop (`concat` with a `year` column, groupby re-aggregate per year, stable-sorted).
- [ ] **Step 4: Run green** — `uv run pytest tests/test_lodes.py -v`.
- [ ] **Step 5: Commit** — `git commit -m "feat(pipeline): per-state multi-year LODES panel fetch (one xwalk, loud 404s)"`

---

### Task 9: `job_accessibility_by_year` (vectorized)  [offline]

**Files:**
- Modify: `src/pipelines/lodes.py`
- Test: `tests/test_lodes.py`

**Interfaces:**
- Produces: `job_accessibility_by_year(zctas_gdf, tracts_gdf, lodes_panel_df, utm_zone, decay_km=GRAVITY_DECAY_KM) -> pd.DataFrame[ZCTA5CE, year, job_accessibility]` — decay matrix computed once, multiplied against an (n_tract × n_years) jobs matrix on the **union tract axis** (0-filled tract-years); tract rows stable-sorted by `trct` before the reduction (issue #6).

- [ ] **Step 1: Failing tests** — (a) hand-computable two-tract case per year (jobs differ by year; assert `A_iy = jobs_Ay + jobs_By·e^{-1}` for each year, `np.isclose`); (b) **`np.allclose` equality with the existing single-year `job_accessibility`** for a shared year on the same synthetic geometry (NOT byte-equality — pairwise-summation groupings differ; design §2); (c) a tract present only in one year contributes 0 in the others.
- [ ] **Step 2: Run** — expected `AttributeError`.
- [ ] **Step 3: Implement** — pivot `lodes_panel_df` to tract×year jobs (union axis, `fillna(0)`), sort by `trct`, one `(n_zcta × n_tract) @ (n_tract × n_years)` product, melt to long.
- [ ] **Step 4: Run green.**
- [ ] **Step 5: Commit** — `git commit -m "feat(pipeline): vectorized multi-year gravity accessibility (allclose-pinned to single-year)"`

---

### Task 10: `TTW_MIDPOINTS` extraction + `fetch_acs_commute_zcta`  [offline]

**Files:**
- Modify: `src/pipelines/acs.py`
- Test: `tests/test_acs.py` (append)

**Interfaces:**
- Produces: `TTW_MIDPOINTS: dict[str, float]` module constant (the 12 bin midpoints currently inlined at `acs.py:233-245`); `compute_acs_features` rewritten to consume it with **identical output** (unit-tested equality on an existing fixture); `fetch_acs_commute_zcta(state_fips: str, year: int) -> pd.DataFrame[ZCTA5CE, commute_min_proxy, ttw_total]` — B08303 at ZCTA geography, state-nested query form first, **national-pull-and-filter fallback** if the endpoint rejects `in=state` (design §Data-availability; the live probe is Task 13's preflight).

- [ ] **Step 1: Failing tests** — (a) `compute_acs_features` output on the existing ACS fixture is unchanged after the refactor (snapshot the fixture output before refactoring, same golden discipline as Task 1); (b) `fetch_acs_commute_zcta` on a monkeypatched Census-API JSON response: proxy = Σ(count × midpoint)/total using `TTW_MIDPOINTS`, ZCTA5CE zero-padded, `ttw_total` int; (c) zero-worker ZCTA → proxy NaN-safe (dropped, matching the existing division guard at `acs.py:214-216`).
- [ ] **Step 2: Run** — expected failures on missing names.
- [ ] **Step 3: Implement** — keep the request plumbing consistent with `fetch_acs_for_county` (same session/key handling).
- [ ] **Step 4: Run green** — `uv run pytest tests/test_acs.py -q` (all pre-existing tests must stay green — the refactor is output-invariant).
- [ ] **Step 5: Commit** — `git commit -m "feat(pipeline): ZCTA-altitude ACS commute fetch with shared TTW midpoints"`

---

### Task 11: Panel flow LODES/ACS half + validators + manifests  [offline]

**Files:**
- Modify: `src/pipelines/panel.py`, `src/pipelines/schema.py`
- Test: `tests/test_flow_structure.py`, `tests/test_schema.py`, `tests/test_panel_pipeline.py`

**Interfaces:**
- Produces: `fetch_state_lodes_panel_task(state_postal, years)` and `fetch_acs_commute_zcta_task(states, year)` (cacheable; **per-state** LODES granularity bounds retry blast radius and year-append cost — design §2 task table); `lodes_panel_task(state_frames, zctas_in_metro, tracts, utm_zone)` (plain CPU: concat, full ZCTA×year grid with 0-fill for fetched-but-absent ZCTAs, `job_accessibility_by_year`, stable-sort); `acs_commute_2019_task(acs_df, zctas_in_metro)` (filter to metro set, rename to `commute_min_proxy_2019`/`ttw_total_2019`, sort); `validate_lodes_panel` / `validate_acs_commute_2019` in `schema.py` (dup keys, `job_count >= 0`, `year ∈ LODES_PANEL_YEARS`, `min(job_accessibility) > 0`, `0 < commute_min_proxy_2019 < 180` — design §3 sanity + §5); flow writes both CSVs + manifests (`years` provenance via Task 5's builder).

- [ ] **Step 1: Failing tests** — flow-structure: both new tasks in the cache-key/TASK_SOURCE tests; schema: validator violation matrix (mirroring Task 3); panel-pipeline: `lodes_panel_task.fn` grid test (metro ZCTA absent from WAC → `job_count=0` for that ZCTA-year; grid is exactly |ZCTAs|×|years| rows) and `acs_commute_2019_task.fn` filter test.
- [ ] **Step 2: Run** — expected import failures.
- [ ] **Step 3: Implement** — flow calls the per-state task in a list comprehension over `states_for_counties(COUNTIES)`; note in the flow docstring that Prefect runs the mapped calls concurrently under the default task runner.
- [ ] **Step 4: Run green** — `uv run pytest -q` (entire suite; cross-sectional untouched).
- [ ] **Step 5: Commit** — `git commit -m "feat(pipeline): LODES panel + ACS-2019 vintage wired into build_panel_flow"`

---

### Task 12: `panel_gate.py` LODES + ACS sections  [offline]

**Files:**
- Modify: `scripts/panel_gate.py`
- Test: `tests/test_panel_gate.py`

**Interfaces:**
- Produces: `check_lodes_panel(baseline, new, accept_access_drift=False) -> GateResult` — append-only: existing `(ZCTA5CE, year)` cells must have **byte-identical `job_count`** (string compare under `dtype=str`; no escape hatch — an upstream reissue must be investigated) and `job_accessibility` within `FLOAT_NOISE_RTOL` (max relative delta always reported; `--accept-access-drift` waives for the reviewed geometry-vintage case — design §3); new years append at the tail only. `check_acs_commute_2019(baseline, new)` — `ttw_total_2019` byte-identical, proxy at rtol, no hatch. New-data sanity: per-year Spearman ρ(access, `distance_to_cbd_km` from the 35-column file) < 0; `min(job_accessibility) > 0`.

- [ ] **Step 1: Failing tests** — matrix: identical PASS; `job_count` +1 on an existing cell FAIL (with and without every accept flag — no bypass); access delta at 1e-13 PASS with reported max-delta; access delta at 1e-6 FAIL then PASS under `accept_access_drift=True`; new year appended PASS; a *removed* year FAIL; ACS proxy drift FAIL.
- [ ] **Step 2: Run** — expected `AttributeError`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run green** — `uv run pytest tests/test_panel_gate.py -v`.
- [ ] **Step 5: Commit** — `git commit -m "feat(gate): LODES/ACS append-only checks — int byte-identity, float rtol, reviewed drift hatch"`

---

### Task 13: Availability preflight + live LODES/ACS build ×9, commit data  [NETWORK]

**Files:**
- Modify: `data/final/lodes_panel_*.csv` ×9, `data/final/acs_commute_2019_*.csv` ×9 (+18 manifests)

- [ ] **Step 1: Preflight probe (design §Verification 5)** — HEAD-probe all `LODES_PANEL_YEARS` × 11 states (99 WAC URLs; a ~15-line throwaway script in the scratch dir is fine — do not commit it): expected 200 ×99; abort on any 404 with the full missing list and re-scope `LODES_PANEL_YEARS` before building. Then probe the ACS 2019 ZCTA query shape with the repo's keyed machinery (one state, one variable): if state-nesting is rejected, flip `fetch_acs_commute_zcta` to its national-pull fallback **before** the build and note it in the PR.
- [ ] **Step 2: Phoenix build + gate** — `METRO=phoenix uv run python run_pipeline.py --panel` (warm ZORI cache from Task 7 makes this LODES/ACS-dominated; expect ~1–4 min). Immediate rebuild → `panel_gate.py`: expected LODES/ACS identical (`job_count` byte-equal; access max-delta ≲ 1e-15 same-environment), ZORI unchanged.
- [ ] **Step 3: All nine** — `--panel --all` (~10–30 min cold; design §2 corrected estimate). Then `run_pipeline.py --verify` (OK ×27) and full `uv run pytest -q`.
- [ ] **Step 4: Sanity spot-checks** — per metro: `lodes_panel` row count == |ZCTAs| × 9; 2019-vs-2021 access Spearman ρ high (>0.95 — the vintages should mostly agree in ordering); `acs_commute_2019` coverage ≥ 90% of the metro ZCTA set (ACS ZCTA universe is near-complete; investigate if lower — likely the 2010/2020 code-match margin, quantify and note).
- [ ] **Step 5: Commit + Phase-2 PR**

```bash
git add data/final/lodes_panel_*.csv data/final/acs_commute_2019_*.csv data/final/*.manifest.json
git commit -m "feat(data): commit LODES accessibility panels + ACS-2019 commute vintage x9"
```

PR body carries: preflight probe output, gate output, the 2019-vs-2021 access correlation table.

---

# Phase 3 — RQ4 analysis module + reporting

### Task 14: `panel_fe.py` — within estimator with honest inference  [offline]

**Files:**
- Create: `src/models/panel_fe.py`, `tests/test_panel_fe.py`

**Interfaces:**
- Produces: `within_fe(y, X, unit_ids, time_ids, cluster_ids) -> FEResult` (frozen dataclass: `params`, `bse`, `cov`, `n_obs`, `n_units`, `dof_note`) — demeans y and X within unit AND time (two-way, via iterated demeaning or explicit month dummies demeaned within unit — pick the LSDV-provable one), OLS with `cov_type="cluster"`, then rescales the covariance by `(N−K)/(N−K−G_absorbed)`. `dof_note` documents the convention: **deliberately conservative — the Cameron–Miller/reghdfe convention omits nested absorbed FE from K; we inflate instead** (design §4 Estimator layer 2). Also `wald_joint(result, idx) -> (stat, p)`.

- [ ] **Step 1: Failing tests**

```python
"""LSDV-equality and inference tests for the within-FE estimator."""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from src.models.panel_fe import within_fe


def _synthetic_panel(seed: int = 7, n_units: int = 30, n_periods: int = 24):
    rng = np.random.default_rng(seed)
    unit = np.repeat(np.arange(n_units), n_periods)
    time = np.tile(np.arange(n_periods), n_units)
    x = rng.normal(size=unit.size) + 0.5 * (unit % 5)          # unit-correlated regressor
    a_i, g_t = rng.normal(size=n_units), rng.normal(size=n_periods)
    y = 2.0 * x + a_i[unit] + g_t[time] + rng.normal(scale=0.5, size=unit.size)
    return y, x[:, None], unit, time


def test_within_equals_lsdv_coefficients_and_clustered_ses() -> None:
    y, X, unit, time = _synthetic_panel()
    fe = within_fe(y, X, unit, time, cluster_ids=unit)

    dummies = np.column_stack([
        pd.get_dummies(unit, drop_first=True).to_numpy(dtype=float),
        pd.get_dummies(time, drop_first=True).to_numpy(dtype=float),
    ])
    lsdv = sm.OLS(y, np.column_stack([X, dummies, np.ones_like(y)])).fit(
        cov_type="cluster", cov_kwds={"groups": unit}
    )
    assert np.allclose(fe.params[0], lsdv.params[0], rtol=1e-8)
    # SE equality under the STATED convention: LSDV counts absorbed dummies in K,
    # which is exactly what the within path's explicit rescale reproduces.
    assert np.allclose(fe.bse[0], lsdv.bse[0], rtol=1e-6)


def test_known_effect_recovery_ci_covers() -> None:
    hits = 0
    for seed in range(20):
        y, X, unit, time = _synthetic_panel(seed=seed)
        fe = within_fe(y, X, unit, time, cluster_ids=unit)
        lo, hi = fe.params[0] - 1.96 * fe.bse[0], fe.params[0] + 1.96 * fe.bse[0]
        hits += lo <= 2.0 <= hi
    assert hits >= 17          # ~95% coverage, generous band for 20 draws


def test_small_cluster_count_no_nan() -> None:
    y, X, unit, time = _synthetic_panel(n_units=6)
    fe = within_fe(y, X, unit, time, cluster_ids=unit)
    assert np.isfinite(fe.bse).all()
```

- [ ] **Step 2: Run** — expected `ModuleNotFoundError`.
- [ ] **Step 3: Implement** (~80 lines; statsmodels only).
- [ ] **Step 4: Run green** — `uv run pytest tests/test_panel_fe.py -v`.
- [ ] **Step 5: Commit** — `git commit -m "feat(models): within-FE estimator, LSDV-pinned coefficients and clustered SEs"`

---

### Task 15: Webb wild cluster bootstrap  [offline]

**Files:**
- Modify: `src/models/panel_fe.py`
- Test: `tests/test_panel_fe.py`

**Interfaces:**
- Produces: `wild_cluster_boot_p(y, X, unit_ids, time_ids, cluster_ids, coef_idx, n_boot=999, seed=...) -> float` — restricted (null-imposed) wild cluster bootstrap with Webb 6-point weights over clusters; used for flagged thin-identification metros and the ZIP3 coarse-cluster spatial robustness (design §4 Estimator layer 3). ~30 lines of numpy.

- [ ] **Step 1: Failing tests** — (a) under a true null (B=0 synthetic panel, 12 clusters), rejection rate at 5% over 40 seeds lands in a coarse [0, 0.15] band; (b) under a strong effect, p < 0.05; (c) degenerate guard: < 3 clusters raises `ValueError`; (d) deterministic under fixed seed.
- [ ] **Step 2: Run** — expected `AttributeError`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run green** (mark the rejection-rate test `@pytest.mark.slow` if it exceeds ~30 s; the repo runs slow tests in CI).
- [ ] **Step 5: Commit** — `git commit -m "feat(models): Webb wild cluster bootstrap for thin-cluster inference"`

---

### Task 16: Loader, fixtures, `RQ4Results`  [offline]

**Files:**
- Modify: `src/models/data_loader.py`, `src/models/results.py`, `tests/conftest.py`
- Test: `tests/test_data_loader.py`, `tests/test_rq4.py` (create)

**Interfaces:**
- Produces: `PANEL_FILES = {"zori": "zori_panel_{metro}.csv", "lodes": "lodes_panel_{metro}.csv", "acs2019": "acs_commute_2019_{metro}.csv"}`; `load_panel_data(metro, final_dir) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]` (Utf8 ZCTA5CE, validators applied, raises on invalid); frozen `RQ4Results` with the design-§5 field list; conftest gains `sample_panel_fixtures` — a synthetic (zori_panel, lodes_panel, acs2019, cross_df) quadruple with ~30 ZCTAs × 60 months spanning the break, a planted donut effect (positive distance×Post1 interaction), and a few post-2019 entrant ZCTAs (feeds Tasks 17–19).

- [ ] **Step 1: Failing tests** — loader round-trip on tmp CSVs (dtype pinning: write a `08501` ZCTA, assert it survives as a string); loader raises on an invalid panel; `RQ4Results` frozen (assigning raises `FrozenInstanceError`).
- [ ] **Step 2–4:** standard red → implement → green (`uv run pytest tests/test_data_loader.py tests/test_rq4.py -q`).
- [ ] **Step 5: Commit** — `git commit -m "feat(models): panel loader with pinned dtypes + RQ4Results contract"`

---

### Task 17: `analyze_rq4` — Spec A family  [offline]

**Files:**
- Create: `src/models/rq4_rent_dynamics.py`
- Test: `tests/test_rq4.py`

**Interfaces:**
- Produces: `analyze_rq4(cross_df, zori_panel, lodes_panel, acs2019_df) -> RQ4Results` covering the Spec-A family (design §4): merged estimation frame (log zori; **pre-COVID interaction set**: `commute_min_proxy_2019`, `distance_to_cbd_km`, log `job_accessibility_2019` from the LODES panel's 2019 rows); `ENDPOINT_TRIM_MONTHS` trim; two-phase headline (`POST1 = 2020-03..2021-12`, `POST2 = 2022-01..`) joint + three singles + pooled summary; transition-window drop (2020-03..05) **co-headline**; 2021-vintage robustness (35-column proxy + LODES 2021 access); balanced subpanel (in-sample by 2019-01); entrant-composition table; `n_identifying` + `under_identified` flag (< 20) triggering bootstrap p-values; ZIP3 coarse-cluster bootstrap robustness.

- [ ] **Step 1: Failing tests** (against the Task-16 fixtures):

```python
def test_rq4_recovers_planted_donut_effect(sample_panel_fixtures) -> None:
    cross, zp, lp, acs = sample_panel_fixtures
    r = analyze_rq4(cross, zp, lp, acs)
    d = r.gradient_models_single["distance_to_cbd_km"]
    assert d["post1_coef"] > 0                       # planted repricing found...
    assert d["post1_pvalue"] < 0.05                   # ...and significant


def test_rq4_headline_uses_2019_vintage_not_2021(sample_panel_fixtures) -> None:
    """Fixture plants DIFFERENT 2019 and 2021 commute proxies; the headline
    interaction must load on the 2019 one (design §4: pre-treatment measurement)."""
    cross, zp, lp, acs = sample_panel_fixtures
    r = analyze_rq4(cross, zp, lp, acs)
    assert r.gradient_model_joint["x_vintage"] == "2019"
    assert "vintage2021" in r.vintage2021_robustness


def test_rq4_endpoint_trim_and_transition_drop(sample_panel_fixtures) -> None:
    cross, zp, lp, acs = sample_panel_fixtures
    r = analyze_rq4(cross, zp, lp, acs)
    assert r.n_post_months < zp["period"].n_unique()  # trim + drop actually removed months


def test_rq4_flags_thin_identification(sample_panel_fixtures_thin) -> None:
    """A fixture with 8 identifying ZCTAs must flag and carry bootstrap p."""
    cross, zp, lp, acs = sample_panel_fixtures_thin
    r = analyze_rq4(cross, zp, lp, acs)
    assert "under_identified" in r.flags
    assert "distance_to_cbd_km" in r.bootstrap_pvalues
```

- [ ] **Step 2–4:** red → implement (analyze = pure computation, no I/O) → green.
- [ ] **Step 5: Commit** — `git commit -m "feat(rq4): two-phase structural-break estimation on the pre-COVID gradient"`

---

### Task 18: `analyze_rq4` — event study + Specs C / C-med / D  [offline]

**Files:**
- Modify: `src/models/rq4_rent_dynamics.py`
- Test: `tests/test_rq4.py`

**Interfaces:**
- Produces (design §4): event study on **event-time bins relative to 2020-03** (base 2019-03..2020-02; 12-month pre bins; 6-month post bins through 2022-02, 12-month after) with per-bin identifying counts in `event_study`; Spec C (annual access merged by year, truncated 2023-12, no carry-forward) + robustness (2-yr-averaged access; drop 2020/21 LODES years); Spec C-med mediation decomposition (share of Post1 repricing absorbed by contemporaneous access, labeled as mediation, never "robustness"); Spec D annual collapse **requiring ≥ 6 months per (i, y)**, lagged + **lead falsification** + contemporaneous + long differences (2015→2019, 2019→2023).

- [ ] **Step 1: Failing tests** — (a) bin edges: 2020-01/02 fall in the **base** bin, 2020-03 in the first post bin (assert directly on the bin-assignment helper); (b) event_study frame carries `n_identifying` per bin; (c) Spec C estimation window max period == 2023-12 (no carry-forward rows); (d) Spec D drops (i,y) cells with < 6 months (plant one); (e) lead-term model present in results (`chase_model_lead`); (f) mediation dict has `share_mediated` ∈ [-1.5, 1.5] on the fixture.
- [ ] **Step 2–4:** red → implement → green (`uv run pytest tests/test_rq4.py -q`).
- [ ] **Step 5: Commit** — `git commit -m "feat(rq4): event-time event study, access specs, mediation, predictive-association Spec D"`

---

### Task 19: `report_rq4` + `run_rq4` + `run_analysis.py` wiring  [offline]

**Files:**
- Modify: `src/models/rq4_rent_dynamics.py`, `run_analysis.py`
- Test: `tests/test_rq4.py`, `tests/test_reporting_output.py`

**Interfaces:**
- Produces: `report_rq4(results, out_dir, fig_dir, metro)` — `rq4_summary_<metro>.md` with: coefficient/Wald/bootstrap tables (phase 1/2 + pooled), event-study figure (per-bin identifying counts on secondary axis), entrant-composition table, and the **mandatory caveats block** (ZIP≈ZCTA + ZCTA-2010≈2020, coverage bias, sorting-vs-pricing, no-causal-claim, estimand statement — design §4 caveats, §6); `run_rq4(...)` composition; `run_analysis.py` gains `HAS_RQ4` optional-import (mirroring the `HAS_RQ2`/`HAS_RQ3` pattern at `run_analysis.py:39-49`) and **skips with a log line when any panel file is absent** (exit 0, RQ1–RQ3 unaffected).

- [ ] **Step 1: Failing tests** — report writes the file with the caveat block present (grep for "not a causal", "covered-ZCTA", "listing"); figure file exists; `run_analysis` skip test: point it at a tmp final-dir with only the 35-column CSV → RQ4 skipped, exit 0, log line emitted (capsys/caplog).
- [ ] **Step 2–4:** red → implement → green; then full `uv run pytest -q`.
- [ ] **Step 5: Commit** — `git commit -m "feat(rq4): reporting with mandatory honesty rails + optional-import wiring"`

---

### Task 20: RQ4 smoke on real committed panels  [offline — needs Phases 1–2 data merged/present]

- [ ] **Step 1:** `uv run python run_analysis.py --metro PHX` — expected: RQ1–RQ4 all complete; `data/processed/PHX/rq4_summary_PHX.md` exists with populated tables; no under-identified flag for phoenix (92 identifying ZCTAs).
- [ ] **Step 2:** Checkout-simulation: temporarily move `data/final/zori_panel_phoenix.csv` aside, re-run — expected: RQ4 skip line, exit 0; restore the file.
- [ ] **Step 3:** `uv run python run_analysis.py --metro MEM` — expected: `under_identified` flag set, bootstrap p-values in the summary, no crash at 39 clusters/12 identifying.
- [ ] **Step 4: Commit** any smoke-revealed fixes with their own tests: `git commit -m "fix(rq4): <what the smoke run surfaced>"` (empty step if clean). Open the Phase-3 PR.

---

# Phase 4 — Findings + docs

### Task 21: Full analysis run + findings §10  [NETWORK for the one-off SA comparison only]

**Files:**
- Modify: `docs/findings.md`

- [ ] **Step 1:** `uv run python run_analysis.py --all` — 9 metros complete, `rq4_summary_*.md` ×9.
- [ ] **Step 2: SA one-off robustness (design §4 Index choice)** — local `--panel` build against `ZORI_ZIP_CSV_URL` into the scratch dir (do NOT commit; a temporary URL override argument or env var is acceptable throwaway plumbing), re-run RQ4 for 2–3 metros (PHX, LA, CHI), record the coefficient deltas + the pull vintage in findings.
- [ ] **Step 3:** Write **findings §10 "RQ4 — COVID and the Commute Gradient (ZORI Dynamics)"** (findings.md currently ends at §9): the estimand statement verbatim (design §4 Diagnostics); cross-metro z-scored table of Post1/Post2 interaction coefficients with Wald + bootstrap p and `n_identifying`; event-study takeaways with pre-trend verdicts per metro; MEM flagged; SA-vs-non-SA comparison; the deferred-list pointer. Executive summary gains one RQ4 bullet.
- [ ] **Step 4: Commit** — `git commit -m "docs: findings §10 — COVID commute-gradient repricing from the ZORI panel"`

### Task 22: README + pipeline docs + archive  [offline]

**Files:**
- Modify: `README.md`, `RUNNING_PIPELINE.md`, `src/pipelines/PIPELINE_README.md`

- [ ] **Step 1:** README: data-sources table + ZORI-panel row (non-SA + revision-gate note) and ACS-2019 row; new "Panel data products" subsection (3 files × 9 metros, gate semantics one-liner); architecture mermaid + `panel.py`.
- [ ] **Step 2:** RUNNING_PIPELINE.md: `--panel` usage, panel outputs table, gate/escape-hatch procedure (review-only contract). PIPELINE_README.md: panel flow step list.
- [ ] **Step 3:** `grep -rn "sm_sa_month\|--panel\|zori_panel" README.md RUNNING_PIPELINE.md src/pipelines/PIPELINE_README.md` — no stale/missing claims.
- [ ] **Step 4: Commit + PR; after merge, archive:**

```bash
git mv docs/plans/2026-07-17-rq4-zori-dynamics-design.md docs/plans/2026-07-17-rq4-zori-dynamics-plan.md docs/archive/
git commit -m "chore: archive implemented rq4 zori dynamics design + plan"
```

---

## Verification Summary (per phase)

| Phase | Gate |
|-------|------|
| 1 | `uv run pytest` green throughout (no red window — panel products are additive); `panel_gate.py` calibration double-build PASS with recorded revision stats; `run_pipeline.py --verify` OK ×18; ZORI CSVs + manifests committed together; ruff clean; CI green on PR |
| 2 | 99-URL preflight all-200 + ACS query-shape probe resolved; gate PASS (job_count byte-identical on double-build); `--verify` OK ×27; full pytest green incl. non-vacuous tracked-manifest test; 2019-vs-2021 access ρ table in PR |
| 3 | `tests/test_panel_fe.py` LSDV coef+SE equality + recovery + bootstrap green; `tests/test_rq4.py` green; full suite green; PHX and MEM smokes clean (skip-when-absent verified) |
| 4 | `run_analysis.py --all` completes ×9; findings §10 complete with estimand statement + SA comparison; no stale doc claims; both docs archived after merge |
