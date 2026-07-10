# Engineering Hardening — Design

**Date:** 2026-07-09
**Status:** Approved design, pending implementation plan
**Scope:** Resilience, provenance, reproducibility, and test-trust improvements to the existing pipeline. **No new analytical results.**

---

## Guiding Constraint

Every change is **behavior-preserving for the outputs**: the same `data/final/*.csv`, the same figures, the same `docs/findings.md` conclusions. This work hardens *how* results are produced (orchestration resilience, provenance, one-command reproducibility, test coverage of the statistical core) — it does not change *what* the analysis concludes.

Prefect is adopted **local-only**: flows run in-process, no server / agent / deployment required. The Prefect UI (`prefect server start`) is an optional developer convenience, never a runtime or CI dependency. CI continues to run offline with network-marked tests skipped, exactly as today.

---

## Current State (verified)

- `src/pipelines/build.py::build_final_dataset(metro_key)` is a single ~270-line monolith that runs 8+ ETL steps sequentially, holding all intermediate GeoDataFrames/DataFrames in local variables.
- `src/pipelines/utils.py` already provides adapter-level HTTP retry (`urllib3.Retry`, total=3, backoff, `status_forcelist=[429,500,502,503,504]`).
- The analysis layer is already split for testability: `analyze_rq{1,2,3}(df) -> RQ{1,2,3}Results` (pure, no I/O) is separate from `report_rq{1,2,3}(...)` (writes markdown/CSV/figures), with `run_rq*` composing the two. Typed containers live in `src/models/results.py`.
- `prefect>=2.14.0` is declared in `pyproject.toml` but has **zero imports** — a fully dead dependency.
- CI gate: `--cov-fail-under=40`. The coverage `omit` list excludes `rq1/rq2/rq3`, `visualization.py`, `results.py`, and all pipeline orchestration/network modules — i.e. the statistical code that produces the findings is entirely uncovered.
- `.env` is correctly gitignored (only `.env.example` tracked) — no secret leak.
- `data/models/` is empty (`.gitkeep` only); no ML layer (out of scope here).

---

## Scope

Four items, delivered in phases. Confirmed decisions:

- **Prefect:** adopt, local-only, Prefect **3.x**.
- **Cache TTL:** result-persistence cache expires after **7 days**.
- **Coverage gate target:** raise `--cov-fail-under` from 40 to **~70** (pinned just below the achieved number once tests land).

---

## 1. Orchestration Resilience (Prefect 3.x)

Bump the pin: `prefect>=2.14.0` → `prefect>=3.0`.

### Task decomposition

Refactor `build_final_dataset` into `@task`-decorated step functions wrapped in `@flow def build_metro_flow(metro_key)`. Each task preserves the exact logic of its current step:

| Task | Kind | Retries |
|------|------|---------|
| `fetch_cbsa_boundary(cbsa_code)` | network | yes |
| `fetch_state_zctas(zip_prefixes)` | network | yes |
| `fetch_tracts(counties)` | network | yes |
| `filter_zctas(zctas_all, cbsa_boundary, utm)` | cpu | no |
| `fetch_acs(counties)` → `compute_acs_features` | network + cpu | yes (fetch) |
| `fetch_demographics(counties)` → `compute_demographic_percentages` | network + cpu | yes (fetch) |
| `map_tracts_to_zctas(...)` | cpu | no |
| `aggregate_commute(...)` / `aggregate_demographics(...)` | cpu | no |
| `fetch_zori(url)` | network | yes |
| `compute_transit_density(...)` | network (OSM, slow) | yes |
| `compute_pop_density(...)` | cpu | no |
| `merge_and_finalize(...)` | cpu + write | no |

**Constraint:** the extracted task bodies call the existing `src/pipelines/*` functions unchanged. This is a wrapping/orchestration refactor, not a rewrite of the ETL logic.

### Retries

`@task(retries=3, retry_delay_seconds=[5, 15, 45])` on the ~6 network tasks. This composes *above* the existing urllib3 adapter retry: the adapter absorbs per-request transient blips; Prefect retries the whole step on failure. No duplicated configuration — the two layers address different failure granularities.

### Checkpoint / resume

- Result **persistence** enabled with a `cache_key_fn` keyed on `(metro_key, task_name, args_hash)`.
- Persisted to a gitignored `.prefect_cache/` (add to `.gitignore`), with a **7-day TTL** so stale ACS/ZORI/OSM pulls auto-refetch.
- Effect: a mid-run failure re-run skips already-completed fetch steps. Given a full run is 5–15 min of flaky external calls, this is the core resumability payoff.
- OSMnx's own `.cache/` is untouched.
- `PREFECT_HOME` is set to a project-local directory (via Makefile / `.env.example`) so Prefect's SQLite metadata and ephemeral API stay self-contained and offline-friendly.

### `--all`

`run_pipeline.py --all` invokes a parent flow `build_all_metros` that loops `build_metro_flow` per metro, isolating per-metro failure (matches current behavior) and returning a structured result set for the run summary.

---

## 2. Structured RunResult + Dataset Provenance

*(Single artifact satisfying both the "structured run summary" part of item 1 and the "dataset versioning/packaging" item.)*

### Manifest

Each metro pipeline run writes `data/final/<metro>.manifest.json`:

```json
{
  "metro_key": "phoenix",
  "git_commit": "<sha>",
  "run_timestamp_utc": "2026-07-09T…Z",
  "acs_vintage": "ACS 5-Year 2021",   // sourced from acs.DEFAULT_ACS_YEAR, not hardcoded
  "zori_period": "<period from ZORI file>",
  "source_urls": { "acs": "…", "zori": "…", "tiger": "…" },
  "output_csv": "final_zcta_dataset_phoenix.csv",
  "row_count": 147,
  "columns": [ { "name": "rent_to_income", "dtype": "float64" }, … ],
  "sha256": "<hex>",
  "steps": [ { "name": "fetch_acs", "status": "completed", "duration_s": 12.3 }, … ]
}
```

- Manifests are committed (provenance record traceable to a data snapshot + git commit).
- A `verify-data` target recomputes each CSV's sha256 and flags drift vs. its committed manifest.

### Schema contract

New `src/pipelines/schema.py` defining the final-dataset contract:

- Required column set + dtypes.
- Value ranges: percentage/share columns ∈ [0, 100], `rent_to_income` ∈ (0, ~2], densities and counts ≥ 0, `income_segment` ∈ {low, medium, high}.
- A `validate_final_dataset(df) -> None` (raises on violation) wired into **both** `merge_and_finalize` (fail fast on bad pipeline output) and `data_loader.load_and_validate_data` (fail fast on bad analysis input).

---

## 3. One-Command Reproducibility

### Makefile

| Target | Action |
|--------|--------|
| `setup` | `uv sync` |
| `pipeline` | build all metros; skip a metro whose manifest is < 7 days old unless `FORCE=1` |
| `analyze` | run analysis flow over all metros |
| `test` | `uv run pytest` |
| `lint` | `uv run ruff check src/ tests/` |
| `verify-data` | recompute checksums, diff vs committed manifests |
| `all` | `setup` → `pipeline` → `analyze` |
| `clean` | remove `.prefect_cache/`, `.cache/`, coverage artifacts |

### `--all` on `run_analysis.py`

Mirror `run_pipeline.py --all`. Analysis becomes a small `@flow analyze_all_metros` looping `analyze_metro_flow(metro)`, replacing the README bash for-loop and giving both pipeline halves the same orchestration model.

### Determinism

Thread `RANDOM_STATE` (env, default 42) through K-Means (RQ2) and any CV shuffle in `models.py`. Add a test: run `analyze_rq2` twice on the same fixture, assert identical cluster labels.

---

## 4. Analytical-Logic Coverage

### Un-omit the statistical core

Remove from the coverage `omit` list: `rq1_housing_commute_tradeoff.py`, `rq2_equity_analysis.py`, `rq3_aci_analysis.py`, `reporting.py`, `results.py`. Keep omitting only genuinely network/integration modules (pipeline fetch steps, `run_*.py`) — though Phase 2/3 flow tests will cover some of those incidentally.

### New tests

- `tests/test_rq1.py`, `test_rq2.py`, `test_rq3.py` — call `analyze_*` on small synthetic fixtures with tractable values and assert:
  - **RQ1:** AIC-based model selection direction; commute coefficient sign; VIF > 1; finite CV-RMSE; `RQ1Results` field shapes.
  - **RQ2:** ANOVA significance flags (`ANOVAResult.significant`); K-Means `cluster_labels` shape = n rows; `n_clusters` respected; interaction-model presence.
  - **RQ3:** the identity `ACI == z(rent_to_income) + z(commute_min_proxy)`; tier-summary bins; quantile-result tau keys {0.25, 0.5, 0.75}; feature-name list.
- `tests/test_reporting.py` — call `report_*` to `tmp_path` with the `Agg` matplotlib backend; assert expected `.md`/`.csv`/`.png` files exist and markdown contains the expected section headers/tables.

### Gate

Raise `--cov-fail-under` 40 → ~70 (final number pinned just below achieved coverage). Update the CI badge/README note accordingly.

---

## Phasing

Each phase is independently mergeable and lands green.

| Phase | Content | Risk | Verification |
|-------|---------|------|--------------|
| 0 | Housekeeping: commit `docs/findings.md`; resolve deleted `.claude/skills/*` (restore or intentionally remove + commit); Prefect 3 pin | trivial | `uv sync`, CI green |
| 1 | Analytical-logic coverage (item 4) — first, so it protects the refactor | low | new tests pass; gate raised; CI green |
| 2 | Prefect refactor of `build.py` (item 1: tasks, flow, retries, cache) | medium | **output CSV byte-identical** to a pre-refactor run for one metro (e.g. Phoenix), modulo nothing; unit-test the flow with mocked fetchers |
| 3 | Manifest/provenance + schema contract + `verify-data` (items 1+4) | low | manifest emitted; `make verify-data` passes; schema rejects a bad fixture |
| 4 | Analysis flow + `--all` + Makefile + determinism (item 3) | low | `make all` reproduces outputs; determinism test passes |

Rationale for ordering: coverage first gives the Prefect refactor a real test net; the risky refactor (Phase 2) sits in the middle with an explicit output-diff gate; provenance and reproducibility build on the stabilized orchestration.

---

## Explicitly Out of Scope

- Interactive dashboard (`src/dashboard/`), predictive ML layer (`data/models/`), new analytical variables (job density / distance-to-CBD), pooled cross-metro model, longitudinal analysis. These are separate specs.
- PyPI-style packaging. "Packaging" here means reproducible, checksummed, provenance-stamped data snapshots — not distribution.
- Migrating Prefect to a hosted/server deployment. Local execution only.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Prefect refactor silently changes output | Phase 2 gate: byte-identical CSV diff for a reference metro before merge |
| Result persistence of large GeoDataFrames is slow/heavy | Local-only, gitignored, 7-day TTL; `make clean` clears it; disabled in tests/CI |
| Prefect 3 tries to reach a server / writes global state | Project-local `PREFECT_HOME`; ephemeral local API; no deployment |
| Coverage target unreachable without brittle mocks | Target set *after* tests land, just below achieved; only the pure `analyze_*`/reporting layer is required to hit ~70 |
| Determinism gaps surface as flaky tests | Explicit `RANDOM_STATE` plumbing + a twice-run equality test |
