# Running the Data Pipeline

## Quick Start

The data pipeline builds ZCTA-level datasets for each metro area by fetching Census ACS data, Zillow rent data, and OpenStreetMap transit stops.

```bash
# Run pipeline for default metro (Phoenix)
python run_pipeline.py

# Or set a specific metro via environment variable
METRO=dallas python run_pipeline.py

# Run pipeline for all metros sequentially
python run_pipeline.py --all

# Build the RQ4 panel data products instead (composes with --all)
python run_pipeline.py --panel
python run_pipeline.py --panel --all
```

See [Building the RQ4 Panel Data Products](#building-the-rq4-panel-data-products---panel) for what `--panel` builds and how its gate works.

## Available Metro Areas

The pipeline can build datasets for nine metro areas (county lists live in `METRO_CONFIGS` in `src/pipelines/config.py`):

| Metro Key | Metro Area | CBSA Code | ZIP Prefixes |
|-----------|------------|-----------|--------------|
| `phoenix` | Phoenix-Mesa-Chandler, AZ | 38060 | 85 |
| `memphis` | Memphis, TN-MS-AR | 32820 | 38, 72 |
| `los_angeles` | Los Angeles-Long Beach-Anaheim, CA | 31080 | 90, 91 |
| `dallas` | Dallas-Fort Worth-Arlington, TX | 19100 | 75, 76 |
| `denver` | Denver-Aurora-Lakewood, CO | 19740 | 80, 81 |
| `atlanta` | Atlanta-Sandy Springs-Alpharetta, GA | 12060 | 30 |
| `chicago` | Chicago-Naperville-Elgin, IL-IN-WI | 16980 | 60, 61, 62 |
| `seattle` | Seattle-Tacoma-Bellevue, WA | 42660 | 98 |
| `miami` | Miami-Fort Lauderdale-Pompano Beach, FL | 33100 | 33 |

## Configuration

### Setting the Metro Area

Edit `src/pipelines/config.py`:

```python
# Select which metro to use (change this to switch metros)
SELECTED_METRO = os.getenv("METRO", "phoenix")  # Any key in METRO_CONFIGS (nine metros)
```

Or use environment variable:

```bash
export METRO=dallas
python run_pipeline.py
```

### Census API Key

Required for fetching ACS data. Set your Census API key:

```bash
# Add to .env file
CENSUS_API_KEY=your_key_here

# Or export directly
export CENSUS_API_KEY=your_key_here
```

Get a free API key at: https://api.census.gov/data/key_signup.html

## Pipeline Steps

The pipeline executes 9 main steps:

### 1. Fetch CBSA Boundary

- Downloads metro area boundary polygon from Census TIGER
- Used for spatial filtering of ZCTAs

### 2. Load ZCTA and Tract Geometries

- Downloads ZCTA (ZIP code) polygons for the state
- Downloads census tract polygons for metro counties
- Filters ZCTAs to those within the metro area

### 3. Fetch ACS Data (Tracts)

- Fetches ACS 5-year data at census tract level
- Variables include:
  - **B25064**: Median gross rent
  - **B19013**: Median household income
  - **B08303**: Travel time to work (13 bins)
  - **B25003**: Housing tenure (owner/renter)
  - **B08201**: Vehicle availability (0, 1, 2+ vehicles)
- Computes derived features:
  - `rent_to_income`: Rent burden ratio
  - `commute_min_proxy`: Weighted average commute time
  - `renter_share`: Percentage renter-occupied units
  - `vehicle_access`: Percentage households with 1+ vehicles

### 4. Fetch Demographics (Tracts)

- **B01001**: Total population by age/sex
- **B03002**: Hispanic/Latino origin and race
- Computes race/ethnicity percentages
- Creates income segments (low/medium/high)

### 5. Map Tracts to ZCTAs

- Uses centroid-based spatial join
- Each tract mapped to the ZCTA containing its centroid
- Handles edge cases and multiple tracts per ZCTA

### 6. Aggregate to ZCTA Level

- Population-weighted aggregation from tracts to ZCTAs
- Computes population density (persons per km²) using UTM projection
- Aggregation strategy:
  - **Weighted mean**: rent_to_income, commute times, percentages
  - **Sum**: Total population
  - **Median**: Median income (population-weighted)

### 7. Fetch Zillow ZORI Data

- Downloads Zillow Observed Rent Index (ZORI) by ZIP code
- Filters to metro-specific ZIP code prefixes
- Uses latest available month

### 8. Compute Transit Stop Density

- Queries OpenStreetMap Overpass API for transit stops
- Filters: `public_transport=platform|stop|station` or `highway=bus_stop`
- Computes `stops_per_km2` for each ZCTA

### 9. LODES Employment Features (Step 6c)

- Downloads LEHD LODES8 WAC (2021) job counts by census block, plus the block→ZCTA/tract crosswalk
- Aggregates jobs to ZCTA and tract level and computes three features:
  - `job_density`: jobs per km² (LODES WAC C000 / ZCTA UTM area)
  - `distance_to_cbd_km`: km from ZCTA centroid to the nearest configured CBD point (dual-CBD for DFW)
  - `job_accessibility`: gravity index Σ jobs·exp(−d/10 km) over metro tracts
- Logged as `STEP 6c` in pipeline output

## Output

The pipeline generates a CSV file in `data/final/`:

```text
data/final/final_zcta_dataset_{metro}.csv
```

### Output Schema (35 columns)

Columns are listed in output order (the `column_order` list in `src/pipelines/build.py`):

| Column | Description | Source |
|--------|-------------|--------|
| `ZCTA5CE` | 5-digit ZCTA code | Census TIGER |
| `rent_to_income` | Median gross rent / median income | ACS B25064, B19013 |
| `pct_rent_burden_30` | % paying 30%+ of income on rent | ACS (derived) |
| `pct_rent_burden_50` | % paying 50%+ of income on rent | ACS (derived) |
| `zori` | Zillow Observed Rent Index ($) | Zillow ZORI |
| `commute_min_proxy` | Weighted avg commute time (min) | ACS B08303 |
| `pct_commute_lt10` | % commuting < 10 min | ACS B08303 |
| `pct_commute_10_19` | % commuting 10-19 min | ACS B08303 |
| `pct_commute_20_29` | % commuting 20-29 min | ACS B08303 |
| `pct_commute_30_44` | % commuting 30-44 min | ACS B08303 |
| `pct_commute_45_59` | % commuting 45-59 min | ACS B08303 |
| `pct_commute_60_plus` | % commuting 60+ min | ACS B08303 |
| `ttw_total` | Total workers (travel time) | ACS B08303 |
| `pct_drive_alone` | % driving alone | ACS B08301 |
| `pct_carpool` | % carpooling | ACS B08301 |
| `pct_car` | % driving (alone + carpool) | ACS B08301 |
| `pct_transit` | % using public transit | ACS B08301 |
| `pct_walk` | % walking | ACS B08301 |
| `pct_wfh` | % working from home | ACS B08301 |
| `renter_share` | % renter-occupied housing | ACS B25003 |
| `vehicle_access` | % households with 1+ vehicles | ACS B08201 |
| `total_pop` | Total population | ACS B01001 |
| `pop_density` | Population density (per km²) | Derived from geometry |
| `job_density` | Jobs per km² (LODES WAC C000 / ZCTA UTM area) | LEHD LODES |
| `pct_white` | % non-Hispanic white | ACS B03002 |
| `pct_black` | % non-Hispanic Black | ACS B03002 |
| `pct_asian` | % non-Hispanic Asian | ACS B03002 |
| `pct_hispanic` | % Hispanic/Latino | ACS B03002 |
| `pct_other` | % other race/ethnicity | ACS B03002 |
| `median_income` | Median household income ($) | ACS B19013 |
| `income_segment` | Income tercile (low/medium/high) | Derived |
| `stops_per_km2` | Transit stops per km² | OpenStreetMap |
| `distance_to_cbd_km` | Km from ZCTA centroid to nearest metro CBD point (dual-CBD for DFW) | Derived (config CBD points) |
| `job_accessibility` | Gravity index: Σ jobs·exp(−d/10 km) over metro tracts | LEHD LODES + TIGER |
| `period` | ZORI data month (YYYY-MM-DD) | Zillow ZORI |

## Building the RQ4 Panel Data Products (`--panel`)

`--panel` swaps in a separate Prefect flow (`build_panel_flow` in `src/pipelines/panel.py`) that builds the three committed RQ4 panel files per metro instead of the cross-sectional dataset. The default (no-flag) behavior is unchanged, and the two flows share the cacheable geometry fetch tasks.

```bash
# Panel products for the default metro (phoenix)
uv run python run_pipeline.py --panel

# For a specific metro
METRO=atlanta uv run python run_pipeline.py --panel

# For all nine metros (equivalent: make panel)
uv run python run_pipeline.py --panel --all
```

**Prerequisite:** the metro's committed `final_zcta_dataset_<metro>.csv` must exist — the panel's ZCTA universe is the committed 35-column dataset's ZCTA set (ID membership, never geometric CBSA filtering), and the flow raises `FileNotFoundError` if it is absent. Build the cross-sectional dataset first.

### Panel Outputs

Three CSVs per metro in `data/final/`, each validated against its schema before write and paired with a provenance manifest (`<metro>.zori_panel.manifest.json`, `<metro>.lodes_panel.manifest.json`, `<metro>.acs_commute_2019.manifest.json`) that `run_pipeline.py --verify` checks offline.

- `zori_panel_<metro>.csv` — `[ZCTA5CE, period, zori]`: the full monthly ZORI history from Zillow's smoothed **non-seasonally-adjusted** ZIP series (`Zip_zori_uc_sfrcondomfr_sm_month.csv`, `ZORI_PANEL_CSV_URL` in `config.py`). The committed vintage spans 2015-01-31 through 2026-06-30 (138 months). Missing cells are absent rows, never nulls.
- `lodes_panel_<metro>.csv` — `[ZCTA5CE, year, job_count, job_accessibility]`: the full ZCTA × year grid for 2015–2023 (`LODES_PANEL_YEARS`), with the same gravity accessibility formula as the cross-sectional column.
- `acs_commute_2019_<metro>.csv` — `[ZCTA5CE, commute_min_proxy_2019, ttw_total_2019]`: the frozen pre-COVID commute vintage from ACS 5-year 2015–2019 B08303 at ZCTA altitude.

Row counts from the committed `data/final/` files:

| Metro | `zori_panel` rows | `lodes_panel` rows | `acs_commute_2019` rows |
|-------|------------------:|-------------------:|------------------------:|
| `atlanta` | 12,137 | 1,053 | 117 |
| `chicago` | 9,950 | 2,619 | 289 |
| `dallas` | 13,888 | 1,710 | 186 |
| `denver` | 8,218 | 927 | 103 |
| `los_angeles` | 17,969 | 2,430 | 267 |
| `memphis` | 2,661 | 468 | 51 |
| `miami` | 14,338 | 1,620 | 180 |
| `phoenix` | 13,289 | 1,350 | 148 |
| `seattle` | 10,323 | 1,350 | 149 |
| **Total** | **102,773** | **13,527** | **1,490** |

`zori_panel` counts move with the Zillow vintage (ZIPs enter as markets clear Zillow's listing threshold, and thin markets are occasionally retracted). `lodes_panel` is exactly metro ZCTAs × 9 years. `acs_commute_2019` covers the committed ZCTAs present in the 2019 ACS ZCTA release, which can be slightly fewer than the metro's ZCTA count (e.g., Chicago 289 of 291).

### Panel Gate and Escape Hatches

`scripts/panel_gate.py` compares regenerated panels in `data/final/` against a committed baseline copy, with different semantics per product (Zillow revises history between pulls; LODES8 files and the 2019 ACS release are immutable):

- **ZORI — snapshot-replace:** each rebuild replaces the committed panel wholesale with one coherent Zillow vintage. The gate checks schema (never waivable), no lost months, ZCTA churn ≤ 5%, lost cells ≤ 1% over the intersection ZCTA set, and reports revision stats (count, median, p99, max of |Δ|/baseline) — failing only if > 1% of overlapping cells revise beyond 5% or any single cell revises beyond 25%.
- **LODES — append-only:** `job_count` must be byte-identical on existing `(ZCTA5CE, year)` cells (**no escape hatch** — a change means an upstream reissue to investigate); `job_accessibility` is compared at float-noise tolerance (`FLOAT_NOISE_RTOL = 1e-12`) with the max relative delta always reported; new years may append at the tail only. Sanity: `job_accessibility > 0` and, per year, Spearman ρ(access, CBD distance) < 0.
- **ACS 2019 — frozen vintage:** `ttw_total_2019` byte-identical, `commute_min_proxy_2019` within float-noise tolerance, ZCTA set unchanged in both directions. **No escape hatch** — a change means our query or midpoints changed.

Procedure for a deliberate panel rebuild:

```bash
# 1. Snapshot the committed baselines
mkdir -p /tmp/panel_baseline
cp data/final/zori_panel_*.csv data/final/lodes_panel_*.csv \
   data/final/acs_commute_2019_*.csv /tmp/panel_baseline/

# 2. Regenerate the panels
uv run python run_pipeline.py --panel --all

# 3. Gate the regenerated files against the baseline
uv run python scripts/panel_gate.py /tmp/panel_baseline
```

Escape hatches exist for legitimate upstream changes, and **all of them are review-only**: the PR that uses one must quote the gate's output (waived lines included) so a human reviews exactly what was waived.

| Flag | Waives |
|------|--------|
| `--accept-revisions` | The ZORI revision-tolerance check only |
| `--accept-structural` | ZORI structural checks (lost months / churn / lost cells) for a deliberate rebaseline (e.g., Zillow retracts or truncates history) — never the schema check |
| `--accept-access-drift` | The LODES `job_accessibility` float-tolerance check, for the geometry-vintage-change case |

## Running All Metros

To rebuild datasets for all nine metros, use the `--all` flag:

```bash
uv run python run_pipeline.py --all
```

This will sequentially process all nine metros and provide a summary of successes and failures at the end.

Alternatively, you can use a loop with environment variables:

```bash
for metro in phoenix memphis los_angeles dallas denver atlanta chicago seattle miami; do
    echo "Building $metro..."
    METRO=$metro python run_pipeline.py
done
```

## Requirements

### Python Packages

- pandas >= 2.0.0
- geopandas >= 0.14.0
- shapely >= 2.0.0
- pyproj >= 3.6.0
- requests >= 2.31.0
- python-dotenv >= 1.0.0

Install:

```bash
uv sync
```

### External Dependencies

- **Census API Key** (required): https://api.census.gov/data/key_signup.html
- **Internet connection** for API requests:
  - Census TIGER/ACS APIs
  - Zillow ZORI CSV download
  - OpenStreetMap Overpass API

## Logging

The pipeline logs progress to console with INFO level messages:

```bash
INFO - ============================================================
INFO - STEP 1: Fetch CBSA boundary
INFO - Fetching CBSA polygon for code: 38060
INFO - CBSA boundary loaded: Phoenix-Mesa-Chandler, AZ
INFO - ============================================================
INFO - STEP 2: Load ZCTA and tract geometries
INFO - Fetching ZCTAs for state: 04
```

## Performance

Expected runtime per metro (with warm caches):

- **Phoenix**: ~2-3 minutes (150 ZCTAs, 2 counties)
- **Memphis**: ~3-4 minutes (52 ZCTAs, 4 counties)
- **Los Angeles**: ~8-10 minutes (270 ZCTAs, 1 large county)
- **Dallas**: ~5-6 minutes (190 ZCTAs, 4 counties)

Factors affecting runtime:

- Number of census tracts
- Number of ZCTAs
- OpenStreetMap query complexity
- Network latency

## Caching

The pipeline uses `.cache/` directory for intermediate results:

- Census geometries
- API responses (where applicable)

To force fresh data:

```bash
rm -rf .cache
python run_pipeline.py
```

## Troubleshooting

### "Census API key not found"

```bash
# Set your API key
export CENSUS_API_KEY=your_key_here

# Or add to .env file
echo "CENSUS_API_KEY=your_key_here" >> .env
```

### "No data returned from Census API"

- Check that your API key is valid
- Verify county FIPS codes in `config.py` are correct
- Some counties may have limited ACS coverage

### "OpenStreetMap Overpass query timeout"

- Large metros (LA) may timeout on Overpass API
- Pipeline will retry with fallback query
- Consider reducing query complexity in `config.py`

### "ZCTA count lower than expected"

- Some ZCTAs filtered out due to being outside CBSA boundary
- Check ZIP_PREFIXES in `config.py` include all relevant prefixes
- Verify CBSA_CODE is correct for the metro

### Import errors

- Ensure running from project root: `python run_pipeline.py`
- Verify all dependencies installed: `uv sync`
- Check that `src/pipelines/` directory exists with all modules

## Module Structure

The pipeline is organized into focused modules:

- **`build.py`** - Main orchestration (run via `__main__.py`)
- **`config.py`** - Metro configurations and constants
- **`tiger.py`** - Census TIGER/Line geometry fetching
- **`acs.py`** - ACS data fetching and feature engineering
- **`demographics.py`** - Demographic data processing
- **`zori.py`** - Zillow rent index fetching
- **`osm.py`** - OpenStreetMap transit stop queries
- **`panel.py`** - RQ4 panel data products (`build_panel_flow`, run via `--panel`)
- **`spatial.py`** - Spatial operations (joins, filtering)
- **`utils.py`** - Shared utility functions

## Output Validation

After running the pipeline, validate the output:

```bash
# Check file exists
ls -lh data/final/final_zcta_dataset_phoenix.csv

# Check row/column counts
python -c "import pandas as pd; df = pd.read_csv('data/final/final_zcta_dataset_phoenix.csv'); print(f'Shape: {df.shape}'); print(f'Columns: {list(df.columns)}')"

# Check for missing values
python -c "import pandas as pd; df = pd.read_csv('data/final/final_zcta_dataset_phoenix.csv'); print(df.isnull().sum())"
```

Expected outputs (row counts from the committed `data/final/` datasets):

- **Phoenix**: 150 ZCTAs × 35 columns
- **Memphis**: 52 ZCTAs × 35 columns
- **Los Angeles**: 270 ZCTAs × 35 columns
- **Dallas**: 190 ZCTAs × 35 columns
- **Denver**: 103 ZCTAs × 35 columns
- **Atlanta**: 117 ZCTAs × 35 columns
- **Chicago**: 291 ZCTAs × 35 columns
- **Seattle**: 150 ZCTAs × 35 columns
- **Miami**: 180 ZCTAs × 35 columns

## Next Steps

After building datasets, run the analysis:

```bash
# Run RQ1 analysis for a metro
python run_analysis.py --metro PHX

# See RUNNING_ANALYSIS.md for details
```

## Contact

For questions about the pipeline: **Charles Coonce** — charlescoonce@gmail.com | [github.com/cdcoonce](https://github.com/cdcoonce)
