# Running the Data Pipeline

## Quick Start

The data pipeline builds ZCTA-level datasets for each metro area by fetching Census ACS data, Zillow rent data, and OpenStreetMap transit stops.

```bash
# Run pipeline for default metro (Phoenix)
python -m src.pipelines

# Or set a specific metro via environment variable
METRO=dallas python -m src.pipelines
```

## Available Metro Areas

The pipeline can build datasets for four metro areas:

| Metro Key | Metro Area | CBSA Code | Counties |
|-----------|------------|-----------|----------|
| `phoenix` | Phoenix-Mesa-Chandler, AZ | 38060 | Maricopa, Pinal |
| `memphis` | Memphis, TN-MS-AR | 32820 | Shelby (TN), Fayette (TN), Crittenden (AR), DeSoto (MS) |
| `los_angeles` | Los Angeles-Long Beach-Anaheim, CA | 31080 | Los Angeles |
| `dallas` | Dallas-Fort Worth-Arlington, TX | 19100 | Dallas, Denton, Collin, Tarrant |

## Configuration

### Setting the Metro Area

Edit `src/pipelines/config.py`:

```python
# Select which metro to use (change this to switch metros)
SELECTED_METRO = os.getenv("METRO", "phoenix")  # Can be: phoenix, memphis, los_angeles, dallas
```

Or use environment variable:

```bash
export METRO=dallas
python -m src.pipelines
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

The pipeline executes 8 main steps:

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

## Output

The pipeline generates a CSV file in `data/final/`:

```
data/final/final_zcta_dataset_{metro}.csv
```

### Output Schema (32 columns)

| Column | Description | Source |
|--------|-------------|--------|
| `ZCTA5CE` | 5-digit ZCTA code | Census TIGER |
| `rent_to_income` | Median gross rent / median income | ACS B25064, B19013 |
| `pct_rent_burden_30` | % paying 30%+ of income on rent | ACS (derived) |
| `pct_rent_burden_50` | % paying 50%+ of income on rent | ACS (derived) |
| `zori` | Zillow Observed Rent Index | Zillow ZORI |
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
| `pct_white` | % non-Hispanic white | ACS B03002 |
| `pct_black` | % non-Hispanic Black | ACS B03002 |
| `pct_asian` | % non-Hispanic Asian | ACS B03002 |
| `pct_hispanic` | % Hispanic/Latino | ACS B03002 |
| `pct_other` | % other race/ethnicity | ACS B03002 |
| `median_income` | Median household income ($) | ACS B19013 |
| `income_segment` | Income tercile (low/medium/high) | Derived |
| `stops_per_km2` | Transit stops per km² | OpenStreetMap |
| `period` | ACS data period (e.g., 2021) | ACS metadata |

## Running All Metros

To rebuild datasets for all four metros:

```bash
for metro in phoenix memphis los_angeles dallas; do
    echo "Building $metro..."
    METRO=$metro python -m src.pipelines
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
pip install -r requirements.txt
# Or
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

```
INFO - ============================================================
INFO - STEP 1: Fetch CBSA boundary
INFO - Fetching CBSA polygon for code: 38060
INFO - CBSA boundary loaded: Phoenix-Mesa-Chandler, AZ
INFO - ============================================================
INFO - STEP 2: Load ZCTA and tract geometries
INFO - Fetching ZCTAs for state: 04
...
```

## Performance

Expected runtime per metro (with warm caches):

- **Phoenix**: ~2-3 minutes (150 ZCTAs, 2 counties)
- **Memphis**: ~3-4 minutes (100 ZCTAs, 4 counties)
- **Los Angeles**: ~8-10 minutes (450 ZCTAs, 1 large county)
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
python -m src.pipelines
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
- Ensure running from project root: `python -m src.pipelines`
- Check `src/pipelines/__init__.py` exists
- Verify all dependencies installed: `pip install -r requirements.txt`

## Module Structure

The pipeline is organized into focused modules:

- **`build.py`** - Main orchestration (run via `__main__.py`)
- **`config.py`** - Metro configurations and constants
- **`tiger.py`** - Census TIGER/Line geometry fetching
- **`acs.py`** - ACS data fetching and feature engineering
- **`demographics.py`** - Demographic data processing
- **`zori.py`** - Zillow rent index fetching
- **`osm.py`** - OpenStreetMap transit stop queries
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

Expected outputs:
- **Phoenix**: 150 ZCTAs × 32 columns
- **Memphis**: ~100 ZCTAs × 32 columns
- **Los Angeles**: ~450 ZCTAs × 32 columns
- **Dallas**: ~190 ZCTAs × 32 columns

## Next Steps

After building datasets, run the analysis:

```bash
# Run RQ1 analysis for a metro
python run_analysis.py --metro PHX

# See RUNNING_ANALYSIS.md for details
```

## Contact

For questions about the pipeline, contact the DAT490 team.
