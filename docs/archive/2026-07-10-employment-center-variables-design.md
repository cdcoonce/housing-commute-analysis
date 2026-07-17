# Employment-Center Variables — Design

**Date:** 2026-07-10
**Status:** Approved design, pending implementation plan
**Scope:** Add three employment variables (`job_density`, `distance_to_cbd_km`, `job_accessibility`) to the pipeline and analysis, sourced from Census LEHD LODES. **This changes analytical results by design** — the goal is to improve model fit in the metros the current models fail on (Phoenix RQ1 R²=0.32 / ACI R²=0.02; polycentric LA and DFW).

---

## Motivation

`docs/findings.md` §8 names "incorporate employment center locations" as a future research direction: commute time predicts rent burden in only 4 of 9 metros, and the worst-fitting metros (Phoenix, LA, DFW) are exactly the polycentric ones where distance-to-jobs structure is not captured by any current variable. The urban-economics literature says a fixed distance-to-CBD measure is necessary but insufficient for polycentric metros; a gravity-based job-accessibility index is the standard complement (Hansen-type access; see HUD Cityscape 21(2) 2019 on CBD measures, Giuliano & Small 1991 on subcenters).

Formal Giuliano–Small subcenter identification is **out of scope** (cutoff-sensitive, big build); the gravity index covers the polycentric signal without discrete center definitions.

---

## Data Source: LEHD LODES8 WAC

- **What:** Workplace Area Characteristics — job counts by 2020 census block (`w_geocode`, Char15). Variable used: `C000` (total jobs), segment `S000`, job type `JT00`, **year 2021** (pairs with the ACS 5-Year 2017–2021 commute data; both describe 2021; LODES year = April 1 snapshot).
- **URLs** (plain HTTPS, no auth, public domain):
  - WAC: `https://lehd.ces.census.gov/data/lodes/LODES8/{st}/wac/{st}_wac_S000_JT00_2021.csv.gz` (~1–5 MB gz/state)
  - Crosswalk: `https://lehd.ces.census.gov/data/lodes/LODES8/{st}/{st}_xwalk.csv.gz` (~10–60 MB gz/state) — maps `tabblk2020` → `zcta` (Char5), `trct` (Char11), and more.
- **Why LODES8:** enumerated on 2020 blocks, which nest exactly in the 2020-vintage ZCTAs the pipeline already uses (TIGERweb ACS2024 layer = 2020 Census ZCTAs). Block→ZCTA aggregation via the crosswalk is exact containment — no areal interpolation, no spatial join.
- **State coverage:** per-metro states derived from `METRO_CONFIGS[metro]["counties"]` state-FIPS values (new `STATE_FIPS_TO_POSTAL` map in `lodes.py`). All states covering the 9 metros are present in LODES8 year 2021. Memphis spans **TN+MS+AR** — the multi-state loop is mandatory, not an optimization.
- **Known data properties handled:** read `w_geocode`/`tabblk2020` as `str` (leading zeros); drop crosswalk rows with blank `zcta` (unpopulated water/park blocks); block-level values are noise-infused by design — we only consume ZCTA- and tract-level sums, where the noise washes out; LODES counts UI-covered + federal jobs (no self-employed/military) — documented in README data-sources table.

---

## The Three Columns

All three are per-ZCTA, null-free by construction, and appended to the existing 32-column contract (→ 35 columns).

### 1. `job_density` (jobs/km²)

Sum `C000` over WAC blocks grouped by crosswalk `zcta`, restricted to the metro's ZCTA set by the existing left-merge onto `zcta_aggregated`. ZCTAs with no WAC rows get **0** (LODES emits a row for every block with ≥1 job; absence means zero jobs). Divide by the same UTM-projected `area_km2` already computed for `pop_density` (keep `area_km2` in the frame until both densities are derived, then drop). Consistent denominator with `pop_density` by construction.

### 2. `distance_to_cbd_km`

Euclidean distance in the metro's UTM CRS from each ZCTA centroid to the metro's CBD point, in km. **New config key** `cbd_points` in every `METRO_CONFIGS` entry: a list of `(lat, lon)` tuples (converted internally to shapely `(x=lon, y=lat)`); distance = **min over points**. DFW gets two points (Dallas CBD, Fort Worth CBD); all other metros one.

**CBD sourcing procedure (implementation step):** use Holian & Kahn's geocoded 1982 Census CBD points (CES WP-11-21; the HUD Cityscape 2019 comparison rates 1982-CBD/city-hall measures above centroid measures) with principal-city city hall as fallback where a point can't be verified. Each coordinate gets a provenance comment in `config.py`. **Sanity gate:** a test asserts every CBD point falls inside its metro's CBSA boundary polygon (offline: point-in-bbox from committed data or a recorded boundary fixture; live check during rebuild).

### 3. `job_accessibility` (gravity index, job-equivalents)

Hansen-type access: for ZCTA *i*, `A_i = Σ_j jobs_j · exp(−d_ij / DECAY_KM)` where *j* ranges over the metro's **census tracts** (job counts = WAC `C000` grouped by crosswalk `trct`; centroids from the tract geometries the flow already fetches), `d_ij` = UTM Euclidean distance. `GRAVITY_DECAY_KM = 10.0`, a named constant in `lodes.py`, documented as the sensitivity knob. Tract altitude keeps the distance matrix small (hundreds × hundreds) and further averages LODES noise.

**Documented limitation:** jobs outside the CBSA's counties are not counted, so edge ZCTAs understate access to neighboring-metro jobs. Acceptable: consistent with every existing ACS variable's county frame.

---

## Pipeline Integration

Follows the established three-tier task template in `build.py`:

| New task | Tier | Notes |
|---|---|---|
| `fetch_lodes_task(states, year)` | cacheable network (`NETWORK_RETRIES` + `_CACHE`) | inputs hashable (tuple of postal codes, int year); wraps `lodes.fetch_metro_lodes()`, which downloads WAC + xwalk per state and returns one slim DataFrame `[zcta, trct, jobs]` (block rows already aggregated; keeps the persisted cache result small — do NOT persist raw xwalks) |
| `employment_features_task(lodes_df, zctas_in_metro, tracts, cbd_points, utm_zone)` | plain CPU (bare `@task`) | GeoDataFrame inputs → not cacheable, cheap anyway; computes all three columns, returns `[ZCTA5CE, job_count, distance_to_cbd_km, job_accessibility]` |

Flow wiring: one fetch call after `fetch_zori_task`, one compute call after step 6b (needs `zcta_area_df`), one more left-merge on `ZCTA5CE` (`.zfill(5)` keys like every other merge), `job_density = job_count / area_km2` derived inline beside `pop_density`, then `job_count`/`area_km2` dropped. Three entries appended to `column_order`.

Supporting changes:

- **`utils.py`:** `http_csv_to_df` cannot decompress gzip-as-payload (requests only auto-decodes transfer-encoding gzip; pandas can't infer compression from `BytesIO`). Add a `compression: str | None = None` parameter passed through to `pd.read_csv` (default preserves existing behavior).
- **`schema.py`:** append the three names to `REQUIRED_COLUMNS` and `_NON_NEGATIVE_COLUMNS`. Docstring "all 32" → "all 35".
- **`manifest.py`:** `_SOURCE_URLS["lodes"] = "https://lehd.ces.census.gov/data/lodes/LODES8/ (WAC S000_JT00 + xwalk)"`; manifest gains `"lodes_year": 2021` (constant `LODES_YEAR` in `lodes.py`, mirroring the `DEFAULT_ACS_YEAR` pattern). `build_manifest` signature/tests updated.
- **`config.py`:** `cbd_points` key ×9 metros with provenance comments; `tests/test_config.py` extended (key present, ≥1 point each, DFW has 2, lat/lon plausible ranges).
- **`tests/test_flow_structure.py`:** add `fetch_lodes_task` to the distinct-cache-key and TASK_SOURCE-component regression tests.

---

## Dataset Rebuild (the contract-break gate)

Extending `REQUIRED_COLUMNS` makes every committed CSV fail `tests/test_schema.py::test_all_committed_datasets_pass_schema` until regenerated — so the contract change **must land together with rebuilt CSVs + manifests** in the same PR.

Procedure:

1. Snapshot the 9 committed CSVs (pre-change baseline).
2. Full live rebuild: `run_pipeline.py --all` (Census key from `.env`).
3. **Byte-identity gate:** for every metro, all ACS/TIGER-derived columns (everything except `zori`, `period`, `stops_per_km2`, and the 3 new columns) byte-identical to baseline; identical row counts and ZCTA sets. This is the same equivalence standard the Prefect refactor was held to. `zori`/`stops_per_km2` drift is expected (live monthly index / continuously-edited OSM) and reported, not silently accepted.
4. New-column sanity per metro: `job_density` ≥ 0 with plausible max (downtown ZCTAs thousands of jobs/km²); `distance_to_cbd_km` min < 3 km (some ZCTA contains the CBD) and max < metro radius; `job_accessibility` strictly decreasing in distance on average (Spearman ρ < 0 vs `distance_to_cbd_km`).
5. `--generate-manifests`, then `make verify-data` green; commit CSVs + manifests together.

---

## Analysis Integration (append-only)

Positional-read constraints from the current reporting code make append order load-bearing: new features go **after** existing ones everywhere.

- **RQ1** (`rq1_housing_commute_tradeoff.py`): add all three to `required_cols` (l.73–74), append to both design matrices + feature-name lists (l.95–106; commute² stays at quad index 1 — `report_rq1` reads `params[2]`/`pvalues[1]` positionally), add to the `model_df` select (l.146–147). VIF table will surface job_density×pop_density and accessibility×distance collinearity — that is reported signal, not a defect; the interpretation section already warns at VIF>5/>10.
- **RQ2** (`rq2_equity_analysis.py`): append all three to the presence-gated controls list (l.100; interaction p-value read at fixed index 3 is unaffected by appended controls). Add one ANOVA: `job_accessibility` by `income_segment`, mirroring the `stops_per_km2` ANOVA block + an `anova_names` entry in `report_rq2` — the equity question "do low-income ZCTAs have worse job access?". **KMeans stays 2-D** (rent × commute) so cluster semantics remain comparable with prior findings.
- **RQ3** (`rq3_aci_analysis.py`): append all three to the `feature_candidates` optional list (l.90). ACI definition itself unchanged. Quantile regression picks up the features automatically.
- **Loader/schema:** no loader change — extra columns already pass through; range checks apply via `_NON_NEGATIVE_COLUMNS`.

Tests: three columns added to the shared `sample_zcta_df` fixture (uniform non-negative draws; this feeds every RQ test); per-RQ assertions that the names appear in `feature_names` when present and that RQ2/RQ3 still run when the columns are dropped (presence-gating), RQ1 raises `ValueError` when dropped (required). `lodes.py` unit tests on synthetic WAC/xwalk fixtures (multi-state concat, blank-zcta drop, str dtypes, zero-fill). Pure-function tests for distance (known geometry, min-over-points for dual CBD) and gravity (hand-computable 2-tract case; decay monotonicity). Note: RQ1's small-sample warning (n < 10·k) already fires on the 20-row fixture; 3 more features keeps it a warning, not an error.

---

## Findings & Docs Refresh

- Re-run `make analyze` for all 9 metros; regenerate `data/processed/` + `figures/`.
- **`docs/findings.md`:** update RQ1/RQ3 tables and takeaways; add a before/after adjusted-R² comparison table per metro. Attribution caveat recorded: RQ1 comparisons are drift-free (all predictors ACS/TIGER/LODES-derived); RQ3 comparisons confound the new variables with `zori`/`stops_per_km2` drift — noted in the table.
- **README:** data-sources table (+LODES row with universe caveat), pipeline-flow + architecture mermaids (+lodes module/step), output-schema table (+3 rows, "~30" → 35), reproducibility section unchanged in substance.
- **RUNNING_PIPELINE.md:** schema table is already stale (lists 30 of 32) — rewrite to the 35-column truth in passing; per-metro "N ZCTAs × 35 columns" lines. **PIPELINE_README.md:** schema table + step list.

---

## Phasing

Phases 1+2 land together as one PR (the contract change and the rebuilt data must move atomically); Phases 3 and 4 are each independently mergeable and green.

| Phase | Content | Verification |
|---|---|---|
| 1 | `lodes.py` + gzip helper + config `cbd_points` + flow tasks + schema/manifest changes + all new unit tests | offline: full pytest green **except** `test_all_committed_datasets_pass_schema` (expected red until Phase 2 in the same PR) |
| 2 | Full 9-metro rebuild; byte-identity gate; new-column sanity checks; manifests | gate passes; `make verify-data` green; full pytest green |
| 3 | Analysis integration (RQ1/RQ2/RQ3 + fixture + tests) | pytest green; single-metro `run_analysis.py` smoke |
| 4 | Full analysis re-run + findings/README/docs refresh | `make analyze` green ×9; findings comparison table complete |

Phases 1+2 land as one PR (contract + data must move together); 3 and 4 may be separate PRs.

---

## Out of Scope

- Giuliano–Small / McMillen formal subcenter identification and `distance_to_nearest_subcenter`.
- Travel-time (network) distances — Euclidean in UTM only.
- LODES 2019 sensitivity pull (2021 is COVID-affected; a robustness re-pull is a documented follow-up, one constant away).
- Sector-level job densities (CNS01–20), RAC/OD files, EPA SLD / HUD Jobs Proximity products (LODES7-vintage, mismatched).
- Dashboard, ML layer, pooled cross-metro model, longitudinal analysis.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Full rebuild drifts zori/OSM columns vs findings | Expected + quantified by the byte-identity gate; RQ1 comparison is drift-free by construction |
| CA/TX xwalk files (~60 MB gz) slow or heavy in cache | Aggregate to `[zcta, trct, jobs]` inside the fetch function before returning; only the slim frame is persisted |
| CBD coordinates wrong/imprecise | Provenance-commented sources + point-in-CBSA sanity test + distance sanity gate (min < 3 km) |
| Gravity decay choice contested | Single named constant; sensitivity documented as follow-up; index is a covariate, not a headline metric |
| New predictors inflate VIF and muddy RQ1 prose | VIF table reports it; interpretation thresholds already in place; that finding is itself informative |
| LODES universe (no self-employed) biases gig-heavy ZCTAs | Documented in README data-sources caveat |
