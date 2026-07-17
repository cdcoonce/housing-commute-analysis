# RQ4: ZORI Rent Dynamics — Design

**Date:** 2026-07-17 (rev 2 — post econometrics + pipeline critique)
**Status:** Design for review, pending implementation plan
**Scope:** Add RQ4 — within-ZCTA rent dynamics from the ZORI monthly panel (2015–present) plus annual job accessibility from LODES8 — per the adopted decision on issue #8 (2026-07-17 comment). Core question: **did COVID reprice the commute gradient?** (2020 structural break; ZCTA + month fixed effects; per metro). Secondary: **do rents chase job growth?** The ACS-wave panel is deliberately deferred until the 2022–2026 5-year release (~Dec 2027).

---

## Motivation

Every existing RQ is cross-sectional: one rent level, one commute proxy, one point in time. The pipeline already downloads Zillow's full monthly ZORI history (2015-01 onward) and throws away everything but the latest month per ZIP (`fetch_zori_latest`, `src/pipelines/zori.py:79-86` — `sort_values` + `groupby("zip").tail(1)`). Keeping the series unlocks within-ZCTA identification: ZCTA fixed effects absorb every time-invariant amenity, and month fixed effects absorb metro-wide shocks and seasonality, so the surviving variation is *relative repricing across ZCTAs over time* — exactly what a COVID structural-break question needs. LODES8 serves annual job counts on constant 2020 blocks for every panel year, so a time-varying job-accessibility regressor comes from machinery (`src/pipelines/lodes.py`) that already exists.

The repo treats ZIP ≈ ZCTA when merging ZORI onto ZCTA geographies (`build.py:290-291` renames `zip` → `ZCTA5CE` and merges directly). **RQ4 keeps and documents that convention** — introducing a ZIP↔ZCTA crosswalk mid-project would make the panel inconsistent with the cross-sectional dataset it joins to.

---

## Data availability (verified 2026-07-17)

| Claim | Verification |
|---|---|
| ZORI ZIP monthly panel spans 2015-01 → 2026-06 (138 months) | Header of `Zip_zori_uc_sfrcondomfr_sm_sa_month.csv` probed live: first date col `2015-01-31`, last `2026-06-30`; 8,477 ZIP rows nationally (~9.8 MB) |
| The **smoothed non-SA** ZIP series exists with the same schema | `Zip_zori_uc_sfrcondomfr_sm_month.csv` probed live 2026-07-17: HTTP 200, 9,771,285 bytes, last-modified 2026-07-16; identical header layout (RegionName + month-end date columns from `2015-01-31`). §4 makes this the panel's primary series |
| LODES8 WAC serves 2015 and 2023 for all 11 states covering the 9 metros | HTTP HEAD probes: `{st}_wac_S000_JT00_{y}.csv.gz` returns 200 for 2015 and 2023 for az/ar/ca/co/fl/ga/il/ms/tn/tx/wa; **2024 returns 404** (not yet published). Endpoint probes only — LEHD has historical missing state-years, so the implementation plan probes **all** `LODES_PANEL_YEARS` × 11 states before the first live build, and the fetch fails loudly per (state, year) on 404 rather than zero-filling |
| ACS 5-year 2015–2019 serves B08303 (travel time to work) at ZCTA altitude | `2019` ∈ `AVAILABLE_ACS_YEARS` (`src/pipelines/acs.py:20`); ZCTA-geography queries are state-nestable through the 2019 acs5 endpoint (hierarchy removed from 2020 onward). Keyless probes are rejected (HTTP "Missing Key"), so the exact query form is **verified at implementation** with the repo's keyed machinery; documented fallback: national `for=zip code tabulation area:*` pull filtered to the metro ZCTA codes |
| Zillow revises history between pulls | ZORI is smoothed (and, in the SA file, seasonally adjusted with factors re-estimated each release), so historical cells shift slightly on every pull (drives the gate design in §3) |
| File sizes (live HEAD probes) | xwalks 2.7–11.4 MB gz per state (~60 MB for all 11); WAC 0.8–6.3 MB gz per state-year. Total cold-build network ≈ 200–250 MB, **WAC-dominated** |
| Panel magnitudes | Computed from a live ZORI pull intersected with the committed per-metro ZCTA sets — table below |

Per-metro coverage (live pull, 2026-07-17; `zctas` = rows in the committed 35-column dataset). Counts derive from the SA pull; the non-SA file shares the same underlying coverage rule (listing-volume threshold), and the Phase-1 live build re-verifies the counts against the non-SA series before commit:

| Metro | ZCTAs | ZIPs in ZORI | Panel obs | Median months/ZIP | ZIPs w/ 2015 obs | ZIPs w/ 2019 obs |
|---|---|---|---|---|---|---|
| Atlanta | 117 | 112 (96%) | 12,135 | 122 | 53 | 86 |
| Chicago | 291 | 204 (70%) | 9,954 | 39 | 25 | 51 |
| Dallas | 190 | 177 (93%) | 13,889 | 66 | 41 | 84 |
| Denver | 103 | 90 (87%) | 8,220 | 102 | 10 | 64 |
| Los Angeles | 270 | 246 (91%) | 17,970 | 66 | 27 | 119 |
| Memphis | 52 | 39 (75%) | 2,660 | 58 | 6 | 12 |
| Miami | 180 | 171 (95%) | 14,341 | 57 | 67 | 73 |
| Phoenix | 150 | 131 (87%) | 13,291 | 137 | 73 | 92 |
| Seattle | 150 | 125 (83%) | 10,324 | 89 | 14 | 68 |
| **Total** | **1,503** | **1,295** | **~102,800** | — | — | — |

Two facts fall out of this table and shape the design: the panel is **heavily unbalanced** (Zillow adds ZIPs as markets clear its listing-count threshold), and the structural-break coefficient is identified only by ZCTAs observed on *both* sides of 2020-03 — approximated by the "ZIPs w/ 2019 obs" column. Memphis (12) is under-identified and gets flagged, not dropped.

---

## Decisions

### 1. Panel data products: three per-metro long files, joined at analysis time

**Files** (per metro, mirroring the `final_zcta_dataset_<metro>.csv` convention):

- `data/final/zori_panel_<metro>.csv` — the ZORI monthly panel (smoothed **non-SA** series; §4).
- `data/final/lodes_panel_<metro>.csv` — the annual LODES accessibility panel.
- `data/final/acs_commute_2019_<metro>.csv` — the pre-COVID commute-gradient vintage (§4: the headline interaction set must not be measured post-treatment).

**Why separate files, not one joined panel:** the sources have different frequencies (monthly vs annual vs one-shot), different revision behavior (Zillow rewrites history; published LODES8 files and the frozen ACS 2019 release are immutable), and therefore different gate semantics (§3). Broadcasting annual values onto months would duplicate each LODES value ~12× and weld the append-only LODES gate to the snapshot ZORI gate. The join keys (`ZCTA5CE`, plus calendar year of `period` for LODES) are trivial at analysis time. Per-metro files (not one 9-metro long file) match every existing data product, keep the gate per-metro, and keep diffs reviewable.

**`.gitignore` (required, or the products silently never commit):** `.gitignore:45-47` ignores `data/final/*` with negations only for `!data/final/final_zcta_dataset_*.csv` and `!data/final/*.manifest.json` — the new manifests would commit while their CSVs stay untracked. Three negations are added:

```
!data/final/zori_panel_*.csv
!data/final/lodes_panel_*.csv
!data/final/acs_commute_2019_*.csv
```

plus a regression test asserting that every committed manifest's `output_csv` is git-tracked (`git ls-files --error-unmatch` per manifest), so this failure class cannot recur.

**`zori_panel_<metro>.csv` columns:**

| Column | Dtype | Notes |
|---|---|---|
| `ZCTA5CE` | str, 5-digit zero-padded | ZIP treated as ZCTA (documented convention) |
| `period` | str, ISO month-end date (`2020-03-31`) | exactly Zillow's column labels |
| `zori` | float64 | > 0; missing cells are **absent rows, never nulls** — `validate_zori_panel` enforces no-null `zori` so the invariant is checked, not just asserted in prose |

Rows sorted stably by `(ZCTA5CE, period)` (stable-sort-before-write, matching the order-invariance convention from issue #6). Only ZCTAs present in the metro's filtered ZCTA set are kept. Expected magnitudes: 2,660 (Memphis) to 17,970 (LA) rows; ~103k total ≈ 3–4 MB committed across 9 files — comfortably git-committable.

**`lodes_panel_<metro>.csv` columns:**

| Column | Dtype | Notes |
|---|---|---|
| `ZCTA5CE` | str, 5-digit zero-padded | |
| `year` | int64 | 2015–2023 (`LODES_PANEL_YEARS`) |
| `job_count` | int64 | ZCTA total jobs; 0-filled **only** for ZCTAs absent from a successfully fetched WAC file (absence = zero jobs, matching `employment_features_task`); a missing/404 (state, year) file raises — it is never zero-filled |
| `job_accessibility` | float64 | gravity index, same formula/decay as the cross-sectional column |

Full grid: metro ZCTA set × 9 years, so 1,503 × 9 ≈ 13.5k rows total (~500 KB). Sorted by `(ZCTA5CE, year)`.

**`acs_commute_2019_<metro>.csv` columns:**

| Column | Dtype | Notes |
|---|---|---|
| `ZCTA5CE` | str, 5-digit zero-padded | |
| `commute_min_proxy_2019` | float64 | same midpoint formula as the 35-column proxy, computed from ACS 5-year 2015–2019 B08303 fetched at **ZCTA altitude** and filtered to the metro's committed ZCTA set |
| `ttw_total_2019` | int64 | workers in the B08303 universe — coverage/weighting diagnostic |

Rows sorted by `ZCTA5CE`. ~1,500 rows / a few KB total. Two documented approximations: (a) ACS 2019 5-year ZCTAs are 2010-delineation; codes are matched directly to the 2020-vintage ZCTA set — the same altitude of approximation as ZIP≈ZCTA, applied uniformly; (b) the 2019 proxy is computed at ZCTA altitude (workers-weighted by construction) while the 35-column 2021 proxy is a tract-mean — the two are **not level-comparable** and the 2019 column is used only as an interaction regressor, never mixed into the 35-column contract.

**Dtype round-trip conventions (pinned, or the gate's dtype check is unimplementable):** `load_panel_data` reads with polars `schema_overrides={"ZCTA5CE": pl.Utf8}` (polars would otherwise infer i64 — harmless for the current 9 metros but a latent leading-zero bug); `scripts/panel_gate.py` reads with pandas `dtype=str` for structural/byte comparisons and `pd.to_numeric` for tolerance comparisons, exactly like `rebuild_gate.py:127-128`.

**Relation to the 35-column dataset:** the cross-sectional file remains the sole carrier of the 2021-vintage regressors (`commute_min_proxy`, `distance_to_cbd_km`, ACS controls) and is joined on `ZCTA5CE` at analysis time. The panel products never duplicate its columns. The 35-column dataset, its schema, and its rebuild gate are **untouched**.

### 2. Pipeline changes: additive panel flow, zero edits to the cross-sectional build path

**`config.py`:** new constant `ZORI_PANEL_CSV_URL = ".../Zip_zori_uc_sfrcondomfr_sm_month.csv"` (smoothed, **non-SA**; §4 rationale). The cross-sectional `ZORI_ZIP_CSV_URL` (SA) is untouched.

**`zori.py`:** extract the existing wide→long tidy logic (currently `zori.py:41-77`) into a module-level helper `tidy_zori(wide_df) -> DataFrame[zip, period, zori]`, then:

- `fetch_zori_latest(url)` — re-expressed as `tidy_zori(...)` + the existing `tail(1)`; **byte-identical output**, proven against a golden fixture generated from the *pre-refactor* code (generated and committed before the refactor lands, or the equality test proves nothing). `fetch_zori_task`'s body in `build.py` does not change, so its `INPUTS + TASK_SOURCE` cache key is unaffected.
- `fetch_zori_series(url, zip_prefixes: tuple[str, ...]) -> DataFrame[zip, period, zori]` — new; tidies then filters to ZIPs matching the metro's `zip_prefixes` (the same config key `fetch_state_zctas_task` uses). Prefix filtering shrinks the Prefect-persisted result from ~1.17M national rows to a few tens of thousands, and makes the task's inputs hashable per metro. Note the cache key is `(url, zip_prefixes)`, which **differs per metro** — a cold `--panel --all` downloads the ~9.8 MB national CSV nine times (~88 MB total, a few minutes). Accepted: the alternative (persisting the unfiltered ~1.17M-row national tidy frame once) violates the cache-size discipline for marginal savings.

**`acs.py`:** extract the B08303 midpoint weights into a module-level `TTW_MIDPOINTS` constant consumed by `compute_acs_features` (output unchanged — unit-tested equality) and by the new `fetch_acs_commute_zcta(state_fips, year) -> DataFrame[ZCTA5CE, commute_min_proxy, ttw_total]`, which queries B08303 at ZCTA geography for one state (state-nested form first; national-pull-then-filter fallback if the 2019 endpoint rejects nesting) and computes the proxy with the shared midpoints.

**`lodes.py`:** the current `fetch_state_jobs` re-downloads the (year-invariant) crosswalk on every call — fine for one year, wasteful ×9. Add:

- `fetch_state_xwalk(state_postal) -> DataFrame` — extracted from `fetch_state_jobs` (which now calls it; output unchanged, so the existing `fetch_lodes_task` cache is again unaffected). Stays an **uncached helper** (persisting raw xwalks violates the cache-size discipline).
- `fetch_state_lodes_panel(state_postal, years: tuple) -> DataFrame[year, zcta, trct, jobs]` — downloads the state's xwalk **once**, then loops the years' WAC files against it; HTTP errors (including a 404 on any single year) **propagate** — a missing state-year is a loud failure, never a silent zero-fill.
- `job_accessibility_by_year(zctas_gdf, tracts_gdf, lodes_panel_df, utm_zone, decay_km)` — vectorized across years: the (n_zcta × n_tract) decay matrix `exp(-D/decay)` is computed once and multiplied against a (n_tract × n_years) jobs matrix on the union tract axis (0-filled for tract-years with no jobs row). Tract rows stable-sorted by `trct` before the reduction (the issue-#6 order-invariance convention). Equality with the existing single-year `job_accessibility` is asserted with `np.allclose` (pairwise-summation groupings differ, so byte-equality is the wrong bar).
- Constants: `LODES_PANEL_YEARS: tuple[int, ...] = tuple(range(2015, 2024))` — 2015 matches the ZORI window start; 2023 is the newest published LODES8 year (extend when 2024 drops; the gate accommodates append-only). `LODES_YEAR = 2021` and the 35-column path are untouched.

**New module `src/pipelines/panel.py`** with `build_panel_flow(metro_key)` — a **separate Prefect flow**, so `build_metro_flow` is not modified at all. It reuses the existing cacheable tasks (`fetch_cbsa_boundary_task`, `fetch_state_zctas_task`, `fetch_tracts_task`, `filter_zctas_task` imported from `build.py`); Prefect's `INPUTS + TASK_SOURCE` cache is flow-agnostic, so a panel build after a dataset build hits cache on all shared fetches. New tasks, following the established tiers:

| Task | Tier | Inputs (hashable for cacheable tier) |
|---|---|---|
| `fetch_zori_series_task(url, zip_prefixes)` | cacheable network (`NETWORK_RETRIES` + `_CACHE`) | str, tuple |
| `fetch_state_lodes_panel_task(state_postal, years)` | cacheable network — **per state**, so a transient failure retries one state (3–10 files), not all 11 states × 9 years, and extending `years` refetches per-state rather than one all-states blob | str, tuple |
| `fetch_acs_commute_zcta_task(states, year)` | cacheable network | tuple, int |
| `zori_panel_task(zori_long, zctas_in_metro)` | plain CPU (`@task`) | DataFrames — not cacheable, cheap |
| `lodes_panel_task(state_frames, zctas_in_metro, tracts, utm_zone)` | plain CPU | concats the per-state frames, builds the full ZCTA×year grid + accessibility |
| `acs_commute_2019_task(acs_zcta_df, zctas_in_metro)` | plain CPU | filters to the metro ZCTA set |

The flow writes the three CSVs (stable-sorted), validates them against the new panel schemas (§5), and emits panel manifests (§3). No `pyarrow`; no `result_storage` on tasks (the documented Prefect 3.x TypeError, `build.py:42-44`).

**CLI:** `run_pipeline.py` gains `--panel` (and `--panel --all`), mirroring the existing flags; `Makefile` gains a `panel:` target. The default (no-flag) behavior is unchanged. **One small owned edit to `--verify`:** `run_pipeline.py:170-172` derives the CSV path as `final_zcta_dataset_{manifest stem}.csv`, which mis-pairs the new manifests (`phoenix.zori_panel.manifest.json` → nonexistent `final_zcta_dataset_phoenix.zori_panel.csv` → guaranteed exit-1 drift). `--verify` is changed to resolve the CSV from the manifest's own `output_csv` field (already recorded by `build_manifest`, `manifest.py:111`), with the current naming convention as fallback for pre-field manifests. The "reused as-is" claim in the previous revision of this design was mechanically false; this is the correction.

**Dev-loop cache note:** `TASK_SOURCE` hashes only the task wrapper body, not module helpers — which is exactly why the `tidy_zori` refactor is cache-safe, but also means that while *iterating* on `tidy_zori`/`fetch_zori_series`/`fetch_state_lodes_panel` under a warm 7-day cache, stale persisted results are served with no invalidation. Documented in `panel.py`'s module docstring: clear `.prefect_cache/` (or bump a `_PANEL_CACHE_SALT` task parameter) when editing panel helper code mid-development.

**Runtime estimate (first live build, cold cache; corrected from live HEAD probes):** total network ≈ 200–250 MB, **WAC-dominated** (xwalks are ~60 MB across all 11 states, not the ~250 MB previously claimed — the `lodes.py:79` "10–60 MB gz" docstring is stale, actual range 2.7–11.4 MB gz). ZORI adds 9 × ~9.8 MB. Per metro ~1–4 min network + parse; **~10–30 min for all nine** (the earlier 20–40 min figure was derived from ~4× overstated crosswalk sizes; kept as a hard upper bound). Warm-cache re-runs: seconds. Persisted cache growth: per-state `(year, zcta, trct, jobs)` frames, a few MB per state — comparable to the existing single-year LODES cache entries.

### 3. Gate semantics for committed panel data: snapshot-replace for ZORI, append-only for LODES/ACS

Zillow **revises history between pulls** (trailing smoothing re-estimates recent months at each release; the SA file additionally re-runs seasonal factors over the full sample). This forces an explicit choice the issue comment glossed as "append-only":

- **Append-only (rejected for ZORI):** freezing committed history and only appending new months means each committed month permanently carries the vintage of whichever pull first included it. The committed series becomes a patchwork of incompatible vintages — *worse* for within-ZCTA estimation than any single coherent pull, and permanently divergent from the upstream source of truth. Byte-stability of history would be an illusion of stability, not the real thing.
- **Snapshot-replace with revision reporting (chosen):** each rebuild replaces the committed panel wholesale with one coherent Zillow vintage. Provenance carries the vintage: the panel manifest records the pull timestamp, the max period, and the month range, so every analysis result is reproducible *as of a recorded pull*. The gate then makes revisions **visible and bounded** instead of pretending they don't happen.

**New `scripts/panel_gate.py`** (separate from `rebuild_gate.py`, whose docstring, `LIVE_COLUMNS`, and sanity checks are 35-column-specific; the existing gate stays untouched). Per metro, comparing committed baseline vs regenerated panel. All checks below name their denominators explicitly so the script is implementable without interpretation:

*ZORI panel — structural violations (FAIL):*
1. Schema violation (columns, dtypes under the pinned read conventions of §1, non-positive `zori`, duplicate `(ZCTA5CE, period)` keys).
2. Lost months: the baseline's period set must be a subset of the new period set.
3. ZCTA churn: |baseline ZCTAs absent from new| / |baseline ZCTAs| must be ≤ 5% (Zillow occasionally retracts thin markets; small churn is reported, wholesale loss fails).
4. Lost cells, computed **over the intersection ZCTA set only** (ZCTAs present in both baseline and new — otherwise any churn that check 3 permits would mechanically trip this check): |(ZCTA, period) cells present in baseline but absent in new, restricted to intersection ZCTAs| / |baseline cells of intersection ZCTAs| must be ≤ 1%.

*ZORI panel — revision policy (REPORT, bounded):* for all overlapping cells, report count, median, p99, and max of |Δ|/baseline. FAIL only if >1% of overlapping cells revise by more than 5%, or any single cell revises by more than 25%. Rationale for the thresholds: routine smoothing re-estimation moves recent cells by ≪1% (and dropping SA removes the largest revision driver); a 5%+ rewrite of history at scale means Zillow changed methodology and a human must look before the data lands. The thresholds are named constants, expected to be calibrated by the first rebuild-over-rebuild run.

*Escape hatches (both reviewed-human-only, mirroring `--accept-drift`):*
- `--accept-revisions` — bypasses the revision-tolerance check only.
- `--accept-structural` — bypasses structural checks 2–4 for the deliberate-rebaseline case (Zillow has retracted/truncated history before, e.g. the 2023 methodology change moved the series start). Without this the gate could never pass after a legitimate upstream truncation and people would hand-edit baselines. It prints exactly which checks it waived; the PR that uses it must quote the gate output. Check 1 (schema) has **no** escape hatch — a malformed panel never lands.

*LODES panel — append-only with a float-honest comparison (the previous revision's pure byte-identity was wrong):* published LODES8 files are immutable, so `job_count` (integer sums of immutable inputs) must be **byte-identical** on existing `(ZCTA5CE, year)` cells; new years may append at the tail. `job_accessibility`, however, is a derived float whose bits depend on BLAS/numpy pairwise-summation behavior — the repo already codified this as `FLOAT_NOISE_RTOL = 1e-12` in `rebuild_gate.py:47-49` because byte-identity on these floats proved unattainable — and on re-fetched TIGERweb tract geometries whose centroids shift when the service updates its vintage. So: `job_accessibility` on existing cells is compared at `FLOAT_NOISE_RTOL`, with the max relative delta always reported; a `--accept-access-drift` escape hatch (reviewed-human-only, same contract as above) exists for the geometry-vintage-change case. Any `job_count` change on an existing cell means an upstream reissue and must be investigated, not absorbed — no escape hatch.

*ACS 2019 file — frozen vintage:* the 2015–2019 release is final; `ttw_total_2019` byte-identical, `commute_min_proxy_2019` at `FLOAT_NOISE_RTOL`. Any larger change fails (a Census API vintage does not revise; a change means our query or midpoints changed).

*New-data sanity (all):* `zori > 0`; panel ZCTA set ⊆ the metro's 35-column ZCTA set; `job_count >= 0`; `min(job_accessibility) > 0` per metro-year (protects the log transform in §4 — a zero would be a high-leverage `-inf`); per-year Spearman ρ(`job_accessibility`, `distance_to_cbd_km`) < 0 (the existing gate's sanity idea, per year); `0 < commute_min_proxy_2019 < 180`.

**Manifests:** `data/final/<metro>.zori_panel.manifest.json`, `<metro>.lodes_panel.manifest.json`, `<metro>.acs_commute_2019.manifest.json`, produced by a new `build_panel_manifest(...)` in `manifest.py` that reuses `_metro_config_snapshot`, `compute_sha256`, the provenance modes, and `cbsa_vintage` — but **not** `_SOURCE_URLS` verbatim: `manifest.py:24` interpolates `LODES_YEAR` (2021) into the lodes source string, which would stamp self-contradictory provenance ("WAC 2021" beside `years: [2015..2023]`). `build_panel_manifest` parameterizes the lodes entry by the years tuple, the zori entry by `ZORI_PANEL_CSV_URL`, and the acs entry by the 2019 vintage; the 35-column manifest path is untouched. ZORI panel manifests add: `pull_timestamp_utc`, `period_min`, `period_max`, `n_months`, `n_zctas`. LODES panel manifests add: `years` (explicit list). `verify_manifest` already checks sha256/row-count/columns generically and is reused as-is; `run_pipeline.py --verify` pairs manifests to CSVs via `output_csv` (§2).

### 4. Econometric specification

All estimation is **per metro**, mirroring every existing RQ. Outcome: `y_it = log(zori_it)` — log because ZORI levels differ ~4× across ZCTAs within a metro and the questions are about *relative* appreciation; coefficients read as approximate percent effects.

**Index choice — smoothed non-SA, not SA:** the panel uses `Zip_zori_uc_sfrcondomfr_sm_month.csv` (verified live, §"Data availability"). Zillow's seasonal factors are re-estimated on the full sample each vintage (two-sided), so current-vintage pre-2020 SA values embed post-2020 data — an anticipation artifact located exactly at the break we are estimating. Sample-month fixed effects already absorb *all* common seasonality, so SA buys nothing here while its look-ahead (and most of the revision churn driving the §3 gate) is pure downside. The SA variant is retained as a one-off robustness comparison at findings time (a local build against `ZORI_ZIP_CSV_URL`; vintage recorded in findings; not committed — committing a second full panel doubles the data products for a single comparison). Residual caveat: the *trailing smoothing* in the `_sm_` series spreads a March-2020 shock over ~3 index months and induces MA errors — clustered SEs remain valid, and the transition-window drop below is **co-headline**, not an afterthought, with quarterly aggregation as a further check.

**Interaction regressors — measured pre-treatment (this rev's most important correction):** the previous revision interacted `Post_t` with the 35-column `commute_min_proxy` (ACS 2017–2021: ~40% of responses from 2020–21, with the B08303 commuter universe shrinking selectively exactly where WFH surged) and `job_accessibility` (`LODES_YEAR = 2021`, an April-2021 COVID snapshot the design itself flags as quirky). Both are partially *outcomes* of the treatment, so the specification conflated "COVID repriced the pre-existing gradient" with "COVID moved the measured gradient," and the stated interpretation ("pre-2020 each ZCTA's rent level embeds the equilibrium commute gradient") failed on its own terms. The headline interaction set is therefore **pre-COVID vintage throughout**:

- `commute_min_proxy_2019` — ACS 5-year 2015–2019, from `acs_commute_2019_<metro>.csv` (§1);
- `distance_to_cbd_km` — pure geometry, vintage-free; from the 35-column file as-is;
- `log job_accessibility_2019` — the 2019 row of `lodes_panel_<metro>.csv` (already being built).

The 2021-vintage variant (35-column `commute_min_proxy` + `LODES_YEAR=2021` accessibility) is **demoted to robustness**, reported as "measured-gradient" sensitivity.

**Sample:** all `(i, t)` cells in the metro's ZORI panel, t ∈ 2015-01 … latest, minus the **endpoint trim**: the final `ENDPOINT_TRIM_MONTHS = 1` month of the pull is dropped from estimation (the last 1–2 months of each vintage revise the most — listing lag plus smoothing endpoints — so endpoint coefficients partly reflect provisional data; the manifest's `pull_timestamp_utc` keeps this reproducible). Break: `2020-03-31` is the first COVID-affected month for a month-end index; the ambiguity vs 2020-04 for a smoothed index is covered by the co-headline transition-window drop (2020-03…2020-05 excluded).

**Spec A — the structural break (headline), two-phase:** the documented post-COVID pattern is non-monotone — donut repricing in 2020–21, partial re-steepening from 2022 (return-to-office). A single Post dummy averages over that path, making a near-zero coefficient uninterpretable ("no repricing" vs "repricing then reversal"). So the headline is two-phase:

```text
log(zori_it) = a_i + g_t + Σ_x [ B1_x (x_i × Post1_t) + B2_x (x_i × Post2_t) ] + e_it

x ∈ {commute_min_proxy_2019, distance_to_cbd_km, log job_accessibility_2019}
Post1_t = 1[2020-03 ≤ t ≤ 2021-12]   (disruption phase)
Post2_t = 1[t ≥ 2022-01]             (partial-RTO phase)
```

- `a_i` = ZCTA fixed effects; `g_t` = **sample-month fixed effects** (one dummy per calendar month in the sample, ~138 levels — absorbing metro-wide shocks *and* seasonality; not month-of-year dummies). Main effects of the x's are absorbed by `a_i`; `Post1/Post2` main effects by `g_t`. Only the interactions are identified — which is exactly the question.
- **"Did COVID reprice the commute gradient?" as testable coefficients:** phase-specific cluster-robust Wald tests on each interaction set. The donut hypothesis predicts **B1_c > 0, B1_d > 0, B1_a < 0** in the disruption phase; the Post2 set answers "did it stick?" (B2 ≈ B1 = persistent repricing; B2 ≈ 0 = full reversal). A pooled single-`Post` variant (`Post_t = 1[t ≥ 2020-03]`) is reported alongside as the summary average, explicitly labeled as averaging over a non-monotone path.
- Because the three gradient variables are mutually correlated (VIF findings from the employment-variables work), report **three single-interaction models plus the joint model**; the joint model is headline, the singles show robustness of sign.
- Reported units: natural units (per minute, per km, per log-point) in the per-metro reports; a within-metro z-scored variant of the three x's in the cross-metro findings table so magnitudes are comparable across metros.

**Spec B — event study (the honesty check on A):** interactions of the x's with **event-time bins defined relative to 2020-03, not calendar years** (calendar-year bins would put pre-break 2020-01/02 into the treated "2020" bin, mechanically attenuating the first post coefficient and blurring the pre-trend test at exactly the year that matters). Base bin: 2019-03…2020-02. Pre bins: 12-month bins counting back from the base (2015-01/02 folded into the earliest bin). Post bins: 6-month bins over 2020-03…2022-02 (the phase structure at finer grain), 12-month bins after. Flat pre-break coefficients support the parallel-trends reading of Spec A; a drifting pre-path demotes Spec A's B's to "trend + break" and is reported as such. This is the headline figure per metro, and the figure reports **per-bin identifying ZCTA counts** on a secondary axis (Denver's earliest bins rest on 10 ZIPs; a reader must see that).

**Spec C — time-varying accessibility (annual regressor in the monthly panel):**

```text
log(zori_it) = a_i + g_t + theta * log(job_accessibility_{i, year(t)}) + e_it,   t ≤ 2023-12
```

`job_accessibility_{i,y}` from the LODES panel, merged by calendar year of `period`. The estimation window ends 2023-12 (last LODES year) — **no carry-forward inside estimation**; carrying 2023 access into 2024–26 months would fabricate zero within-variation and attenuate theta. LODES measurement caveat acted on, not just flagged: robustness with (a) 2-year-averaged access and (b) 2020/2021 LODES years dropped (block-level noise infusion and establishment-geocoding reassignments create spurious within-ZCTA variation that attenuates theta; the COVID-year files are the worst offenders).

**Spec C-med — mediation decomposition (relabeled from the previous revision's "A+C robustness"):** adding contemporaneous access to Spec A conditions the break coefficients on a variable that is itself a COVID outcome — a mediator, not a control, so "does the break survive?" is the wrong question. It is reported instead as an explicit mediation decomposition — "what share of the repricing runs through contemporaneous job relocation?" — with the standard selection-into-mediator caveat stated in the report.

**Spec D — secondary: rents and job growth (annual), written as predictive association:** collapse to annual mean log rent `ybar_iy` over months in year y, **requiring ≥ 6 observed months per (i, y) cell** (thin cells otherwise dominate the annual mean), then

```text
ybar_iy = a_i + g_y + phi * log(job_accessibility_{i, y-1}) + e_iy,   y ∈ 2016…2023
```

FE consistency here would require strict exogeneity, which access does not plausibly satisfy (reverse causality rents→firm location; persistent local demand shocks; lagging does not fix simultaneity under persistence, and with T=8 the within-estimator feedback bias is not negligible). So: (a) `phi` is written up as a **predictive association**, never "rents chase jobs" as a causal claim; (b) a **lead term** `log(job_accessibility_{i, y+1})` is added as falsification — a significant lead means feedback, not chasing; (c) **long-difference** robustness (Δlog rent vs Δlog access over 2015→2019 and 2019→2023) checks the association at a frequency where LODES noise matters less. Contemporaneous variant as robustness. Arellano–Bond and friends stay out of scope.

**Estimator and inference (statsmodels, no new dependency):** two-way FE via the within transform — demean `y` and every regressor (including the month dummies) within ZCTA (Frisch–Waugh–Lovell), then OLS with `cov_type="cluster", cov_kwds={"groups": zcta_codes}` — **SEs clustered by ZCTA**, robust to arbitrary within-ZCTA serial correlation (severe in a smoothed monthly index) — with three layers the previous revision lacked:

1. **Correctness tests:** exact coefficient equality with two-way LSDV on a synthetic panel, **and SE equality under the stated dof convention** (the previous test asserted coefficients only). Known-effect recovery test (inject B1_c, assert CI coverage).
2. **Dof convention, documented as a deliberate choice:** with ZCTA FE nested inside ZCTA clusters, the Cameron–Miller/reghdfe convention *omits* absorbed FE from K in the small-sample correction; this implementation instead rescales the covariance by `(N−K)/(N−K−G_absorbed)` — the opposite, deliberately conservative direction (inflates SEs by <1% at this N). Documented in the module docstring and findings so a reviewer reads it as a choice, not an error.
3. **Spatial dependence and few effective clusters:** ZCTA clustering is robust to serial correlation only; the regressors of interest are spatially smooth (distance-to-CBD mechanically so) and rent shocks correlate across neighboring ZCTAs beyond what month FE absorb — the Barrios–Diamond–Imbens–Kolesár configuration where unit-clustered SEs are understated for spatially aggregated regressors. Robustness: re-cluster at the **3-digit ZIP prefix** level (`ZCTA5CE[:3]` — spatially coherent USPS sectionals, ~4–15 per metro, derivable offline with no new data product) with **wild cluster bootstrap (Webb weights)** p-values, since prefix counts are far below asymptotic-cluster territory. The same bootstrap (at ZCTA level) supplies headline p-values for the flagged thin-identification metros: Memphis has 39 clusters but only ~12 identify the break — the *effective* cluster count for the interactions is ~12 and CR1 t-stats are oversized, so MEM (and any metro whose `n_identifying` < 20) reports bootstrap p-values beside conventional ones. The bootstrap is ~30 lines of numpy in the RQ4 module; no new dependency. County-level clustering and Conley spatial-HAC were considered and argued down (Alternatives).

**Diagnostics reported with the headline (not buried):**

- **Entrant-composition table (signs the entry-selection direction instead of just acknowledging it):** with heavy unbalance, `g_t` is estimated off a changing composition; if Zillow adds peripheral (plausibly high-x) ZCTAs as they thicken, the identifying subsample tilts toward incumbents, likely *attenuating* the donut coefficients. One table per metro: mean of each x for ZCTAs entering the panel after 2019-12 vs incumbents. The balanced-subpanel robustness (ZCTAs observed by 2019-01) remains the bound.
- Per-metro `n_identifying` (ZCTAs observed both pre and post break) and per-bin counts (Spec B figure).
- **Estimand statement (findings §10, verbatim):** unweighted ZCTA-level regression estimates the *average covered-ZCTA* repricing, not renter-weighted repricing; ZORI cells also have listing-volume-dependent precision. A renter-share-weighted variant (weights = `renter_share` × `total_pop` from the 35-column file) is reported as robustness.

**Identification caveats (stated in the report, not buried):**

1. **ZIP ≈ ZCTA** — inherited convention; ZIP delivery routes and ZCTAs disagree at the margin, uniformly across all RQs. Plus, for the 2019 ACS file, ZCTA-2010 ≈ ZCTA-2020 code matching (§1).
2. **Coverage bias** — quantified in the availability table: 70–96% of ZCTAs cross-sectionally, far less pre-2020 (Denver 10/103 in 2015). ZORI requires a minimum listing volume, so the panel over-represents larger, denser rental submarkets; the estimated repricing gradient is for the *covered* submarket.
3. **Endogenous panel entry** — entry correlates with the outcome; see the entrant-composition table and balanced-subpanel bound above.
4. **Sorting vs pricing** — ZORI is a repeat-weighted *listing* index: within-ZCTA composition of listed units can shift (new construction, unit mix). "Repricing" here means the index moved, an amalgam of price and composition change — no hedonic adjustment is possible at this altitude.
5. **No causal claim** — every ZCTA is "treated" by COVID; there is no control group. Spec A estimates within-metro *relative* repricing, descriptive event-study language throughout (see §6).
6. **LODES universe and timing** — UI-covered + federal jobs only (no self-employed); 2020/2021 WAC quirks now acted on via the drop-COVID-years robustness (Spec C); accessibility inherits the county frame's edge bias (documented for the cross-sectional column already).

### 5. Analysis integration

Mirrors the RQ1 module shape exactly (`analyze` = pure computation, `report` = I/O, `run` = composition):

- **`src/models/rq4_rent_dynamics.py`** — `analyze_rq4(cross_df, zori_panel, lodes_panel, acs2019_df) -> RQ4Results` (no I/O; builds the merged estimation frames, runs Specs A/B/C/C-med/D with the robustness suite); `report_rq4(results, out_dir, fig_dir, metro)` (markdown `rq4_summary_<metro>.md` with coefficient/Wald/bootstrap tables, the entrant-composition table, and the caveats block; figures: event-study plot with per-bin identifying counts, pre/post binned gradient plot); `run_rq4(...)`. Internal helpers: the within-FE estimator and the Webb wild cluster bootstrap.
- **`results.py`** — frozen `RQ4Results` dataclass: `gradient_model_joint` (two-phase), `gradient_models_single: dict[str, ...]`, `gradient_model_pooled`, `wald_break: dict` (phase1/phase2/pooled), `bootstrap_pvalues: dict`, `event_study: pl.DataFrame` (variable × bin, coef/se/ci/n_identifying), `access_model`, `mediation: dict`, `chase_model_lagged`, `chase_model_lead`, `chase_model_contemp`, `long_difference: dict`, `vintage2021_robustness: dict`, `n_obs`, `n_zctas`, `n_identifying`, `n_pre_months`, `n_post_months`, `coverage: dict`, `balanced_robustness: dict`, `entrant_composition: pl.DataFrame`, `flags: list[str]` (e.g. `under_identified`).
- **`data_loader.py`** — `PANEL_FILES` mapping + `load_panel_data(metro, final_dir) -> (zori_panel, lodes_panel, acs2019)` (polars, `schema_overrides={"ZCTA5CE": pl.Utf8}`, validated on load).
- **`schema.py`** — additive `validate_zori_panel(df)` / `validate_lodes_panel(df)` / `validate_acs_commute_2019(df)`: required columns, dup-key checks on `(ZCTA5CE, period)` / `(ZCTA5CE, year)` / `ZCTA5CE`, `zori > 0` **and non-null**, `job_count >= 0`, `year` within `LODES_PANEL_YEARS`, ISO-date `period`, `0 < commute_min_proxy_2019 < 180`. `REQUIRED_COLUMNS` and `validate_final_dataset` untouched.
- **`run_analysis.py`** — RQ4 wired behind the same optional-import pattern as RQ2/RQ3 (`HAS_RQ4`); `analyze_metro_flow` passes the final-data dir so RQ4 can load the panel files, and **skips with a log line when panel files are absent** — an old checkout or a partial rebuild still runs RQ1–RQ3 unchanged.
- **`docs/findings.md`** — new **§10 "RQ4 — COVID and the Commute Gradient (ZORI Dynamics)"**: the estimand statement, cross-metro table of the phase-1/phase-2 interaction coefficients (z-scored variant), Wald and bootstrap p, `n_identifying`, event-study takeaways; Memphis flagged as under-identified; the SA-vs-non-SA one-off comparison. Executive summary gains one RQ4 bullet.
- **FE library decision:** `statsmodels` (already a dependency, used by every RQ) via the within transform. `linearmodels.PanelOLS` would be more ergonomic but (a) it is a new `pyproject.toml` dependency for functionality reproducible in ~30 lines, (b) the within-transform is unit-tested for exact coefficient **and SE** equality against LSDV, and (c) the repo's convention is a minimal, already-frozen dependency set (`uv.lock`). Not added.

### 6. Scope boundaries — what RQ4 does *not* claim, and what is deferred

**Not claimed:**
- No causal effect of COVID: no control group exists; results are relative-repricing descriptions within covered rental submarkets.
- No claim about uncovered ZCTAs (the 4–30% per metro without ZORI, systematically thinner rental markets).
- No decomposition of price vs composition (listing-mix) change; no hedonic adjustment.
- No causal "rents chase jobs" claim — Spec D is a predictive association with a lead-term falsification (§4).
- No welfare or affordability-burden claims — the outcome is a rent index, not rent-to-income (income is not observed at monthly frequency).
- No cross-metro pooled estimates — per-metro estimation, cross-metro *comparison* only.

**Deferred:**
- ACS-wave panel (re-scope trigger: 2022–2026 5-year release, ~Dec 2027 — per issue #8).
- LODES 2024+ (append via the panel gate when published); LODES years before 2015 (pre-ZORI, no outcome to pair).
- Dynamic panel estimators for the rents-and-jobs question; spatial spillover/spatial-lag models; Conley spatial-HAC SEs (see Alternatives).
- ZORI tier/segment variants (single-family vs multifamily indexes); metro-level ZORI reconciliation.
- Monthly interpolation of accessibility; travel-time (network) distances.

---

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| One joined monthly panel file (ZORI + broadcast annual LODES) | ~12× duplication of annual values; welds immutable-LODES gate semantics to revisable-ZORI semantics; join at analysis time is one line |
| Single 9-metro long file | Breaks the per-metro file convention every loader/gate/manifest assumes; giant diffs on rebuild |
| Append-only ZORI gate (freeze committed history) | Committed series becomes a patchwork of vintages — statistically worse than any single vintage and permanently divergent from upstream; see §3 |
| Byte-identity gate for ZORI history | Fails on every pull by construction (trailing smoothing); would train everyone to rubber-stamp gate failures |
| Pure byte-identity LODES gate (previous revision) | `job_accessibility` floats are not byte-reproducible across BLAS/numpy versions or TIGERweb geometry vintages — the repo already learned this (`FLOAT_NOISE_RTOL`); byte-identity would fail by construction on the first environment bump, the exact rubber-stamp-training failure mode rejected for ZORI. Ints byte-identical, floats at rtol |
| Keep the 2021-vintage interaction set as headline | Post-treatment measurement: ACS 2017–2021 and LODES 2021 partially embed the COVID response, conflating "repriced the pre-existing gradient" with "moved the measured gradient". Pre-COVID vintages are buildable from machinery this design already creates; 2021 vintage demoted to robustness |
| Fold `commute_min_proxy_2019` into the 35-column dataset | Contract break (35→36) forcing a full cross-sectional rebuild + gate cycle for one analysis-only regressor; a separate frozen-vintage file is additive and independently gated |
| Tract-level ACS 2019 fetch + existing tract→ZCTA aggregation | ACS 2019 5-year tract GEOIDs are 2010-vintage; the pipeline's tract map is 2020-vintage — GEOID renumbering would silently drop/mismatch tracts. ZCTA-altitude fetch avoids the vintage collision entirely; ZCTA-2010≈2020 code matching is the same approximation class as ZIP≈ZCTA |
| Calendar-year event-study bins | 2020-01/02 (pre-break) would sit in the treated "2020" bin, attenuating the first post coefficient and blurring the pre-trend test where it matters most; bins are event-time relative to 2020-03 |
| SA series as primary (previous revision) | Two-sided seasonal factors re-estimated each vintage put post-2020 information into pre-2020 values — an anticipation artifact at the break; month FE already absorb seasonality, so SA is pure cost. Non-SA primary, SA as one-off robustness |
| Committing a second (SA) panel for that robustness | Doubles the committed panel products and gate surface for a single findings-time comparison; a documented one-off local build with recorded vintage suffices |
| County-level clustering for spatial dependence | ZCTAs straddle counties and no committed ZCTA→county product exists; building one adds a data product for a robustness check. 3-digit ZIP prefix clusters are spatially coherent, derivable offline from `ZCTA5CE`, and deliver the same coarser-than-unit clustering; Webb wild bootstrap handles the small cluster counts either way |
| Conley spatial-HAC SEs | Either a new dependency or a nontrivial hand-rolled kernel implementation; the coarse-cluster + wild-bootstrap robustness addresses the same understatement concern at this altitude. Deferred, named in §6 |
| Extend `build_metro_flow` with panel steps | Touches the frozen cross-sectional path for zero benefit; a separate flow shares the Prefect cache anyway and keeps the 35-column gate's blast radius at zero |
| `linearmodels.PanelOLS` | New dependency for ~30 lines of unit-tested within-transform; repo convention is a minimal frozen dependency set |
| Month-of-year FE (12 dummies) | Absorbs seasonality only; sample-month FE (~138) also absorb metro-wide shocks — strictly better for a within-metro relative question, and n is ample |
| Carry 2023 accessibility into 2024–26 months for Spec C | Fabricates zeros in within-variation, attenuating theta; estimation window truncates at 2023-12 instead |
| One `fetch_lodes_panel_task(states, years)` blob task (previous revision) | Whole-task retry re-downloads ~30 files on a transient failure at file 30; extending `years` cold-refetches every metro's every year. Per-state tasks bound the retry blast radius to one state and localize the year-append cost. Per-(state,year) granularity rejected in turn: it would re-download the year-invariant xwalk 9× per state |
| ZIP↔ZCTA crosswalk (UDS mapper) | Would make the panel inconsistent with the entire existing cross-sectional stack; ZIP≈ZCTA is the documented repo-wide convention |
| Post cutoff at 2020-04 | 2020-03 is the first affected month for a month-end index; the co-headline transition-window drop (2020-03…05) covers the ambiguity either way |

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Panel CSVs silently never committed (`data/final/*` gitignore) | Explicit negation lines land with the first panel commit; regression test asserts every committed manifest's `output_csv` is git-tracked |
| Zillow changes the CSV URL/format or retracts history at scale | Gate structural checks fail loudly; manifest pins the last good vintage; `--accept-structural` / `--accept-revisions` each require a human to have looked and the PR to quote gate output (schema check has no bypass) |
| Revision tolerances mis-tuned (gate too noisy or too blind) | Thresholds are named constants in `panel_gate.py`; first rebuild-over-rebuild run calibrates them; escape hatches documented as review-only |
| numpy/BLAS bump or TIGERweb geometry vintage change breaks LODES-gate identity | Ints byte-identical; floats compared at `FLOAT_NOISE_RTOL` with max-delta reporting; `--accept-access-drift` for the reviewed geometry-vintage case |
| A mid-range LODES state-year is missing upstream | Pre-build probe of all `LODES_PANEL_YEARS` × 11 states; fetch raises per (state, year) — a hole in the panel is impossible to create silently |
| ACS 2019 ZCTA query shape wrong (state-nesting) | Verified at implementation with the repo's keyed machinery; documented national-pull fallback; the frozen-vintage gate would catch any later query drift byte-for-byte |
| `--verify` mis-pairs panel manifests | `--verify` resolves CSVs from the manifest's `output_csv` field (owned edit, §2) |
| Memphis under-identification (12 pre-period ZCTAs) misread as a finding | `n_identifying` reported per metro; MEM flagged and reported with wild-bootstrap p-values; no headline claims from flagged metros |
| Unbalanced entry biases the break estimate | Balanced-subpanel (in-sample by 2019-01) robustness next to the headline; entrant-composition table signs the selection direction |
| Within-transform inference subtly wrong | Unit tests: coefficient **and SE** equality vs two-way LSDV; documented conservative dof convention; recovery test with known injected B |
| Warm Prefect cache serves stale results while iterating on panel helpers | Dev note in `panel.py` docstring: clear `.prefect_cache/` or bump `_PANEL_CACHE_SALT` when editing helper code |
| Committed-data growth | ~4–5 MB total across 27 new files (CSVs + manifests) — well within repo norms |
| Panel files absent on old checkouts break analysis | RQ4 optional-import + file-presence skip; RQ1–RQ3 unaffected by construction |

---

## Verification strategy

1. **Unit (offline, monkeypatched HTTP, per repo convention):** `tidy_zori` round-trip + `fetch_zori_latest` byte-equality against a golden fixture generated from *pre-refactor* code; `fetch_zori_series` prefix filtering; `fetch_state_lodes_panel` multi-year aggregation with exactly one xwalk fetch (call-count asserted) and a 404-year raising loudly; `job_accessibility_by_year` hand-computable two-tract case per year + `np.allclose` equality with the existing single-year `job_accessibility` for a shared year; `TTW_MIDPOINTS` extraction leaves `compute_acs_features` output identical; `fetch_acs_commute_zcta` proxy math on a fixture; panel schema validators (dup keys, bad dates, negative values, null `zori`); panel-gate cases (lost month, over-churn, over-tolerance revision, `job_count` change, structural bypass via `--accept-structural`, float-rtol pass on `job_accessibility` → each asserted FAIL/PASS as specified); manifest-tracked-file test.
2. **Econometric correctness:** within-transform == two-way LSDV **coefficients and clustered SEs** (synthetic panel, stated dof convention, `np.allclose`); known-effect recovery (inject B1_c into synthetic data with FE noise, assert CI covers); Webb bootstrap sanity (null rejection rate on synthetic data in a coarse band; degenerate-cluster guard); cluster-SE path smoke (G small, no NaN).
3. **Flow structure:** `fetch_zori_series_task`, `fetch_state_lodes_panel_task`, `fetch_acs_commute_zcta_task` added to the distinct-cache-key and TASK_SOURCE-component regression tests in `tests/test_flow_structure.py`.
4. **Cross-sectional non-regression (the additive guarantee):** full pytest green with **zero changes** to `tests/test_schema.py::test_all_committed_datasets_pass_schema` and the committed 35-column CSVs; `scripts/rebuild_gate.py` untouched; a same-pull consistency check in the panel flow's tests: the last row per ZCTA of `tidy_zori` output equals `fetch_zori_latest` output for the same fixture.
5. **Live availability preflight (before the first LODES build):** HEAD-probe all `LODES_PANEL_YEARS` × 11 states (99 URLs) and the ACS 2019 ZCTA query shape; abort with the full missing list on any 404.
6. **Live smoke (phoenix first, then all nine):** `run_pipeline.py --panel` for phoenix; inspect manifests; run `panel_gate.py` against an immediate second build (expected: ZORI revisions ≈ 0 at same-day vintage, LODES/ACS identical, structural PASS — this is also the tolerance-calibration datapoint); then `--panel --all`, commit panels + manifests together with the gate output in the PR body.
7. **Analysis smoke:** `run_analysis.py --metro PHX` end-to-end with RQ4 present, then a checkout-simulation with panel files removed (RQ4 skips, exit 0).

---

## Design Summary

| # | Decision | Choice |
|---|---|---|
| 1 | Panel products | Three per-metro long CSVs: `zori_panel_<metro>.csv` (~103k rows total, non-SA series) + `lodes_panel_<metro>.csv` (~13.5k rows) + `acs_commute_2019_<metro>.csv` (~1.5k rows); joined at analysis time; `.gitignore` negations + tracked-manifest test; 35-column dataset untouched |
| 2 | ZORI pipeline | Extract `tidy_zori`; `fetch_zori_latest` byte-identical (pre-refactor golden fixture); new `fetch_zori_series(url, zip_prefixes)` against new `ZORI_PANEL_CSV_URL` (smoothed non-SA); per-metro national download accepted (~9× 9.8 MB cold) |
| 3 | LODES panel | `LODES_PANEL_YEARS = 2015–2023`; per-state cacheable task `fetch_state_lodes_panel_task(state, years)`; xwalk fetched once per state (uncached helper); 404s raise per (state, year); full years×states preflight probe; accessibility vectorized (`np.allclose` vs single-year) |
| 4 | Pre-COVID vintage | `acs_commute_2019_<metro>.csv` from ACS 5yr 2015–2019 B08303 at ZCTA altitude (shared `TTW_MIDPOINTS`); access-2019 from the LODES panel; headline interaction set is fully pre-treatment; 2021 vintage demoted to robustness |
| 5 | Flow | New `src/pipelines/panel.py::build_panel_flow`, separate from `build_metro_flow`; ZCTA universe = the committed 35-column dataset (`committed_zcta_frame` — no geometric fetches; ZORI pull is the flow's only network task); `run_pipeline.py --panel`; `--verify` pairs manifests via `output_csv` (owned edit); dev-cache salt note |
| 6 | ZORI gate | Snapshot-replace + revision report; structural checks with explicit denominators (lost-cells over the intersection ZCTA set); tolerance: fail if >1% of cells revise >5% or any cell >25%; `--accept-revisions` + `--accept-structural` (schema check unbypassable); manifest records pull vintage |
| 7 | LODES/ACS gates | Append-only: `job_count`/`ttw_total_2019` byte-identical; float columns at `FLOAT_NOISE_RTOL` with max-delta report; `--accept-access-drift` for geometry-vintage changes; panel manifests parameterize lodes years (no stale 2021 provenance) |
| 8 | Core spec | log non-SA ZORI; ZCTA FE + sample-month FE; pre-COVID {commute_2019, dist-CBD, log access_2019} × {Post1 2020-03..2021-12, Post2 2022-01..} two-phase headline + pooled summary; transition-window drop co-headline; endpoint trim; event study in event-time bins with per-bin identifying counts |
| 9 | Inference | Cluster by ZCTA; LSDV coefficient+SE equality tests; documented conservative absorbed-dof convention; Webb wild cluster bootstrap for flagged metros and ZIP3 coarse-cluster spatial robustness; **no linearmodels dependency** |
| 10 | Time-varying access | Annual log accessibility merged by calendar year, truncated at 2023-12 (no carry-forward); robustness: 2-yr-averaged access, drop 2020/21 LODES; A+C reframed as mediation decomposition; Spec D = predictive association with lead falsification, long differences, ≥6-month annual cells |
| 11 | Analysis surface | `rq4_rent_dynamics.py` + frozen `RQ4Results` + `report_rq4` + optional-import wiring in `run_analysis.py` + findings §10 (incl. estimand statement); panel schemas + loader additive; `ZCTA5CE` read as Utf8 everywhere |
| 12 | Honesty rails | ZIP≈ZCTA (+ ZCTA-2010≈2020) documented; coverage bias quantified; `n_identifying` + entrant-composition table reported; MEM flagged with bootstrap p; sorting-vs-pricing and no-causal-claim caveats in every report |
| 13 | Deferred | ACS-wave panel (~Dec 2027), LODES 2024+, dynamic panels, Conley HAC, spatial-lag models, ZORI tiers, crosswalks, pooled cross-metro model |
