# DAT490 Data Pipeline Documentation

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Architecture](#architecture)
4. [Data Sources](#data-sources)
5. [Module Documentation](#module-documentation)
6. [Configuration](#configuration)
7. [Output Schema](#output-schema)
8. [Troubleshooting](#troubleshooting)
9. [Development](#development)

## Overview

The DAT490 data pipeline is an automated ETL (Extract, Transform, Load) system that aggregates housing affordability, commute patterns, and transit accessibility data at the ZIP Code Tabulation Area (ZCTA) level for major metropolitan areas.

### What It Does

- Fetches geographic boundaries (CBSAs, ZCTAs, census tracts) from Census TIGER/Line
- Retrieves demographic and commute data from Census American Community Survey (ACS)
- Downloads Zillow Observed Rent Index (ZORI) rental price data
- Queries OpenStreetMap for public transit stop locations
- Performs spatial joins and aggregations to combine data sources
- Outputs analysis-ready ZCTA-level datasets

### Key Features

- **Multi-metro support**: Phoenix, Memphis, Los Angeles, Dallas
- **Multi-state metro support**: Handles metropolitan areas spanning multiple states (e.g., Memphis covers TN, MS, and AR)
- **Automated spatial joins**: Tract-to-ZCTA mapping via centroids
- **Population-weighted aggregation**: Accurate demographic rollups
- **API caching**: OSMnx caches OpenStreetMap queries for performance
- **Configurable**: Easy metro switching via environment variables

## Quick Start

### Prerequisites

- Python 3.9+
- Census API Key (recommended): [Get free key](https://api.census.gov/data/key_signup.html)

### Installation

```bash
# Clone repository
git clone https://github.com/PeteVanBenthuysen/DAT490.git
cd DAT490

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env and add: CENSUS_API_KEY=your_key_here
```

### Running the Pipeline

```bash
# Default: Phoenix metro area
python run_pipeline.py

# Specify metro area
METRO=dallas python run_pipeline.py
METRO=memphis python run_pipeline.py
METRO=los_angeles python run_pipeline.py
```

### Expected Output

```text
======================================================================
DAT490 Housing Affordability Data Pipeline
======================================================================

Configuration:
  Metro: phoenix
  Census API Key: ✓ Set

Building dataset for: Phoenix-Mesa-Chandler, AZ
Fetched CBSA boundary
Fetched 150 ZCTAs and 1009 tracts
Fetching ACS commute data for 2 counties...
Processed ACS commute data for 1009 tracts
Fetching ACS demographic data for 2 counties...
Processed demographic data for 1009 tracts
Mapping 1009 tracts to 150 ZCTAs...
Aggregated commute data to 150 ZCTAs
Aggregated demographic data to 150 ZCTAs
Fetching Zillow rent data...
Fetched ZORI data for 41654 ZIP codes
Computing transit density for 150 ZCTAs (may take several minutes)...
Computed transit density for 150 ZCTAs
Created income segments (Low/Medium/High) based on quartiles

SUCCESS: Wrote 150 ZCTAs to final_zcta_dataset_phoenix.csv
   Output: /path/to/DAT490/data/final/final_zcta_dataset_phoenix.csv

======================================================================
Pipeline completed successfully!
Output: /path/to/DAT490/data/final/final_zcta_dataset_phoenix.csv
======================================================================
```

**Processing time**: 5-15 minutes depending on metro size and network speed

## Architecture

### Pipeline Flow

```text
┌─────────────────────────────────────────────────────────────────┐
│                      run_pipeline.py                            │
│                  (Main Entry Point)                             │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    src/pipelines/build.py                       │
│               (Pipeline Orchestration)                          │
└─────┬──────┬──────┬──────┬──────┬──────┬──────┬─────────────────┘
      │      │      │      │      │      │      │
      ▼      ▼      ▼      ▼      ▼      ▼      ▼
   tiger   acs   demo   zori   osm  spatial  utils
     │      │      │      │      │      │       │
     │      │      │      │      │      │       │
     └──────┴──────┴──────┴──────┴──────┴───────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  data/final/*.csv   │
              │   (ZCTA Dataset)    │
              └─────────────────────┘
```

### Data Flow Steps

1. **Geographic Setup** (`tiger.py`)
   - Fetch CBSA boundary polygon
   - Retrieve state ZCTA geometries
   - Retrieve county census tract geometries
   - Filter ZCTAs within CBSA boundary

2. **Census Data** (`acs.py`, `demographics.py`)
   - Fetch ACS commute data (B08303, B08301, B25070)
   - Fetch ACS demographic data (B01001, B03002, B19013)
   - Compute derived features (rent-to-income, commute shares)
   - Calculate demographic percentages

3. **Spatial Join** (`spatial.py`)
   - Map census tracts to ZCTAs using centroid method
   - Handle tract-ZCTA boundary mismatches

4. **Aggregation**
   - Aggregate tract commute data to ZCTA level (mean)
   - Aggregate tract demographics to ZCTA level (population-weighted)

5. **External Data** (`zori.py`, `osm.py`)
   - Fetch Zillow rent index by ZIP code
   - Query OpenStreetMap for transit stops
   - Compute transit density (stops per km²)

6. **Final Merge**
   - Left join all data sources on ZCTA5CE
   - Create income segments (quartile-based)
   - Write CSV to `data/final/`

## Data Sources

### 1. Census TIGER/Line Shapefiles

**Source**: Census Bureau TIGERweb REST API  
**Purpose**: Geographic boundaries  
**Geographies Used**:

- **CBSA (Metro Areas)**: Core-Based Statistical Areas
- **ZCTA (ZIP Codes)**: ZIP Code Tabulation Areas (5-digit)
- **Census Tracts**: Small statistical subdivisions (~4,000 people)

**API Endpoints**:

- CBSAs: `https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/CBSA/MapServer/15/query`
- ZCTAs: `https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS2024/MapServer/2/query`
- Tracts: `https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/7/query`

**No API key required**

### 2. Census American Community Survey (ACS)

**Source**: Census ACS 5-Year Estimates API  
**Purpose**: Demographics, income, commute patterns  
**Dataset**: 2021 ACS 5-Year (most recent with complete data)  
**Geography**: Census tract level  

**Variables Retrieved**:

**Commute Data (B08303 - Travel Time to Work)**:

- Total workers
- Time bins: <5, 5-9, 10-14, 15-19, 20-24, 25-29, 30-34, 35-39, 40-44, 45-59, 60-89, 90+ minutes

**Transportation Mode (B08301 - Means of Transportation)**:

- Drive alone, carpool, transit, walk, other, work from home

**Housing Cost Burden (B25070 - Rent as % of Income)**:

- Rent burden brackets: 30-34%, 35-39%, 40-49%, 50%+

**Demographics**:

- B01001: Total population by age/sex
- B03002: Hispanic/Latino origin and race
- B19013: Median household income

**API Format**:

```text
https://api.census.gov/data/2021/acs/acs5?get=VARIABLES&for=tract:*&in=state:04+county:013&key=YOUR_KEY
```

**Rate Limits**: 500 requests/day without key, unlimited with free API key

### 3. Zillow Observed Rent Index (ZORI)

**Source**: Zillow Research Data  
**Purpose**: Rental price trends  
**Coverage**: Monthly rent index by ZIP code  
**File Format**: Public CSV (no API key needed)

**URL**:

```text
https://files.zillowstatic.com/research/public_csvs/zori/Zip_zori_uc_sfrcondomfr_sm_sa_month.csv
```

**Metric**: Smoothed, seasonally-adjusted rent index for single-family residences, condos, and co-ops

**Data Structure**:

- Columns: RegionName (ZIP), State, Metro, followed by monthly columns (YYYY-MM-DD)
- Values: Typical observed monthly rent in dollars

**Pipeline Usage**: Extracts most recent month for each ZIP code

### 4. OpenStreetMap (OSM)

**Source**: OpenStreetMap via Overpass API  
**Purpose**: Public transit stop locations  
**Tool**: OSMnx Python library  
**Geography**: ZCTA polygons

**Transit Features Queried**:

1. **Primary**: `{"public_transport": True}` - Platforms, stops, stations
2. **Fallback**: `{"highway": "bus_stop"}` - Bus stop nodes

**Metric Computed**: Transit stops per square kilometer

**Caching**: OSMnx automatically caches responses in `.cache/osm/` folder

**Data Completeness**: Varies by region; urban areas typically well-mapped

## Module Documentation

### `config.py` - Configuration & Constants

**Purpose**: Centralized configuration for all pipeline modules

**Key Variables**:

```python
PROJECT_ROOT: Path           # Project root directory
DATA_FINAL: Path            # Output directory for final datasets
CACHE_DIR: Path             # Cache directory for OSMnx
CENSUS_API_KEY: str         # Census API key from environment

METRO_CONFIGS: dict         # Metro area definitions
SELECTED_METRO: str         # Current metro (from METRO env var)
CBSA_CODE: str             # CBSA code for selected metro
COUNTIES: list             # List of (state_fips, county_fips) tuples
ZIP_PREFIXES: list         # ZIP code prefixes for ZCTA queries
UTM_ZONE: int              # UTM EPSG code for area calculations

ZORI_ZIP_CSV_URL: str      # Zillow data URL
FINAL_ZCTA_OUT: Path       # Output CSV path
```

**Metro Configurations**:

The pipeline supports multi-state metropolitan areas. Each metro is defined with a list of counties as `(state_fips, county_fips)` tuples to support metros spanning multiple states (e.g., Memphis spans TN, MS, and AR).

```python
METRO_CONFIGS = {
    "phoenix": {
        "name": "Phoenix-Mesa-Chandler, AZ",
        "cbsa_code": "38060",
        "counties": [
            ("04", "013"),  # Maricopa County, AZ
            ("04", "021")   # Pinal County, AZ
        ],
        "zip_prefixes": ["85"],
        "utm_zone": 32612  # UTM Zone 12N
    },
    "memphis": {
        "name": "Memphis, TN-MS-AR",
        "cbsa_code": "32820",
        "counties": [
            ("47", "157"),  # Shelby County, TN
            ("47", "047"),  # Fayette County, TN
            ("05", "035"),  # Crittenden County, AR
            ("28", "033")   # DeSoto County, MS
        ],
        "zip_prefixes": ["37", "38"],
        "utm_zone": 32616  # UTM Zone 16N
    },
    # ... los_angeles, dallas
}
```

### `build.py` - Pipeline Orchestration

**Purpose**: Main pipeline coordinator executing all ETL steps

**Function**: `build_final_dataset() -> str`

**Returns**: Path to output CSV file

**Steps**:

1. Fetch CBSA boundary
2. Fetch ZCTAs and tracts (supports multi-state queries)
3. Filter ZCTAs to metro area
4. Fetch ACS commute data for all counties (iterates over state-county pairs)
5. Fetch ACS demographic data for all counties (iterates over state-county pairs)
6. Map tracts to ZCTAs (spatial join)
7. Aggregate commute data to ZCTA level
8. Aggregate demographics to ZCTA level
9. Fetch Zillow rent data
10. Compute transit density
11. Merge all data sources
12. Create income segments
13. Reorder columns for consistent output
14. Write output CSV

**Multi-State Support**: The pipeline automatically handles metros spanning multiple states by iterating over the `COUNTIES` list of `(state_fips, county_fips)` tuples. Each state-county combination is queried separately from the Census API and then concatenated.

**Error Handling**: Raises exceptions for API failures, validates data at each step

### `tiger.py` - Geographic Boundaries

**Purpose**: Fetch Census TIGER/Line geographic boundaries

**Functions**:

#### `get_cbsa_polygon(cbsa_code: str) -> gpd.GeoDataFrame`

Fetches metro area boundary polygon

- **Args**: 5-digit CBSA code (e.g., '38060')
- **Returns**: GeoDataFrame with CBSA polygon
- **CRS**: EPSG:4326 (WGS84)

#### `get_state_zctas(zip_prefixes: list[str]) -> gpd.GeoDataFrame`

Fetches ZIP Code Tabulation Areas by prefix

- **Args**: List of ZIP prefixes (e.g., ['85'])
- **Returns**: GeoDataFrame with ZCTA polygons
- **Note**: Queries all states, filters by prefix

#### `get_state_tracts(state_fips: str, county_fips_list: list[str]) -> gpd.GeoDataFrame`

Fetches census tracts for specified counties in a single state

- **Args**: State FIPS code, list of county FIPS codes
- **Returns**: GeoDataFrame with tract polygons
- **Note**: For single-state metros; see `get_tracts_for_counties()` for multi-state support

#### `get_tracts_for_counties(counties: list[tuple[str, str]]) -> gpd.GeoDataFrame`

Fetches census tracts for counties across multiple states

- **Args**: List of (state_fips, county_fips) tuples
- **Returns**: GeoDataFrame with tract polygons concatenated from all states
- **Note**: Supports multi-state metros like Memphis (TN-MS-AR)

### `acs.py` - Census ACS Data

**Purpose**: Fetch and process American Community Survey data

**Functions**:

#### `fetch_acs_for_county(state_fips: str, county_fips: str, year: int = 2021, api_key: str = None) -> pd.DataFrame`

Fetches ACS data for all tracts in a county

- **Args**: State FIPS, county FIPS, year, optional API key
- **Returns**: DataFrame with raw ACS variables
- **Timeout**: 120 seconds
- **Variables**: 50+ ACS variables (commute, mode, rent burden)

#### `compute_acs_features(acs_raw: pd.DataFrame) -> pd.DataFrame`

Computes derived features from raw ACS data

**Derived Metrics**:

- `rent_to_income`: Median rent / median income * 100
- `commute_min_proxy`: Weighted average commute time
- `pct_commute_*`: Percentage in each time bin (lt10, 10_19, 20_29, 30_44, 45_59, 60_plus)
- `pct_*_mode`: Transportation mode percentages
- `pct_rent_burden_30/50`: Rent burden percentages

**Note**: Handles division by zero, missing values

### `demographics.py` - Demographic Data

**Purpose**: Fetch and aggregate demographic data

**Functions**:

#### `fetch_demographics_for_county(state_fips: str, county_fips: str) -> pd.DataFrame`

Fetches race, ethnicity, income data

- **Variables**: B01001, B03002, B19013
- **Returns**: Raw demographic counts

#### `compute_demographic_percentages(demo_raw: pd.DataFrame) -> pd.DataFrame`

Computes demographic percentages

- **Metrics**: pct_hispanic, pct_white, pct_black, pct_asian, pct_other
- **Formula**: (Count / Total Population) * 100

#### `aggregate_demographics_to_zcta(demo_df: pd.DataFrame, tract_to_zcta: pd.DataFrame) -> pd.DataFrame`

Aggregates tract demographics to ZCTA level

- **Method**: Population-weighted averaging
- **Formula**: Σ(value_i × pop_i) / Σ(pop_i)
- **Note**: Uses `include_groups=False` to suppress FutureWarning

#### `create_income_segments(zcta_df: pd.DataFrame) -> pd.DataFrame`

Creates categorical income variable

- **Segments**:
  - Low: Below 25th percentile
  - Medium: 25th to 75th percentile
  - High: Above 75th percentile

### `zori.py` - Zillow Rent Data

**Purpose**: Fetch Zillow Observed Rent Index

**Function**: `fetch_zori_latest(csv_url: str) -> pd.DataFrame`

- **Args**: URL to Zillow CSV
- **Returns**: DataFrame with [zip, period, zori]
- **Logic**:
  1. Downloads full CSV (~40MB)
  2. Identifies most recent month column
  3. Extracts ZIP, date, rent index
  4. Handles missing values

**Output Schema**:

- `zip`: 5-digit ZIP code (string)
- `period`: Date (YYYY-MM-DD format)
- `zori`: Rent index in dollars (float)

### `osm.py` - OpenStreetMap Transit Data

**Purpose**: Query OSM for transit stops and compute density

**Function**: `zcta_transit_density(zcta_gdf: gpd.GeoDataFrame, transit_filter: str, fallback_filter: str) -> pd.DataFrame`

**Process**:

1. Convert ZCTAs to WGS84 (EPSG:4326) for OSMnx
2. For each ZCTA:
   - Query OSM for `{"public_transport": True}`
   - If empty, fallback to `{"highway": "bus_stop"}`
   - Count stop features
3. Compute ZCTA area in UTM projection (meters)
4. Calculate density: stops per km²

**Returns**: DataFrame with [ZCTA5CE, stops_per_km2]

**Error Handling**:

- Network errors: Log warning, continue with 0 stops
- Empty responses: Expected, returns 0 stops
- API version compatibility: Handles both `features_from_polygon` and `geometries_from_polygon`

**Performance**: ~2-5 seconds per ZCTA (varies with network)

### `spatial.py` - Spatial Operations

**Purpose**: Geographic joins and spatial analysis

**Functions**:

#### `filter_zctas_in_cbsa(zctas: gpd.GeoDataFrame, cbsa: gpd.GeoDataFrame) -> gpd.GeoDataFrame`

Filters ZCTAs to those within CBSA boundary

- **Method**: Centroid-based containment check
- **Reason**: Avoids partial overlap issues

#### `tract_to_zcta_centroid_map(tracts: gpd.GeoDataFrame, zctas: gpd.GeoDataFrame) -> pd.DataFrame`

Maps census tracts to ZCTAs via spatial join

- **Method**: Tract centroid → containing ZCTA
- **Returns**: DataFrame with [GEOID, ZCTA5CE]
- **Note**: One tract → one ZCTA (even if boundaries differ)

**Why Centroids?**

Census tract and ZCTA boundaries don't align perfectly. Using centroids ensures:

1. Every tract maps to exactly one ZCTA
2. No double-counting of population
3. Reasonable approximation for aggregation

### `utils.py` - HTTP & Utilities

**Purpose**: Helper functions for data fetching

**Functions**:

#### `http_csv_to_df(url: str) -> pd.DataFrame`

Downloads CSV from URL to DataFrame

- **Timeout**: 180 seconds
- **Returns**: Parsed DataFrame

#### `http_json_to_dict(url: str, params: dict = None) -> dict | list`

Fetches JSON data from URL

- **Returns**: Parsed JSON (dict or list)

#### `esri_geojson_to_gdf(url: str, params: dict) -> gpd.GeoDataFrame`

Fetches geospatial data from ESRI REST API

- **Format**: Handles both ESRI JSON and GeoJSON
- **Returns**: GeoDataFrame in EPSG:4326
- **Used by**: tiger.py for TIGER/Line queries

## Configuration

### Environment Variables

**`.env` file**:

```bash
# Required for reliability (free)
CENSUS_API_KEY=your_census_api_key_here

# Metro area selection (default: phoenix)
METRO=phoenix  # Options: phoenix, memphis, los_angeles, dallas

# Optional: Dashboard configuration
DASHBOARD_PORT=8050
DASHBOARD_DEBUG=True
```

### Metro Area Setup

To add a new metro area, edit `src/pipelines/config.py`. The pipeline supports multi-state metropolitan areas by specifying counties as `(state_fips, county_fips)` tuples:

```python
METRO_CONFIGS = {
    "new_metro": {
        "name": "Full Metro Name",
        "cbsa_code": "12345",           # From Census CBSA definitions
        "counties": [
            ("12", "001"),              # County in primary state
            ("13", "002")               # County in adjacent state (if applicable)
        ],
        "zip_prefixes": ["12", "13"],   # ZIP prefixes for ZCTAs
        "utm_zone": 32617               # EPSG code for UTM projection
    }
}
```

**Multi-State Metro Example** (Memphis, TN-MS-AR):

```python
"memphis": {
    "name": "Memphis, TN-MS-AR",
    "cbsa_code": "32820",
    "counties": [
        ("47", "157"),  # Shelby County, TN
        ("47", "047"),  # Fayette County, TN
        ("05", "035"),  # Crittenden County, AR
        ("28", "033")   # DeSoto County, MS
    ],
    "zip_prefixes": ["37", "38"],
    "utm_zone": 32616
}
```

**Finding Configuration Values**:

- **CBSA codes**: [Census CBSA Delineations](https://www.census.gov/geographies/reference-files/time-series/demo/metro-micro/delineation-files.html)
- **FIPS codes**: [Census FIPS Codes](https://www.census.gov/library/reference/code-lists/ansi.html)
- **UTM zones**: [UTM Zone Map](https://en.wikipedia.org/wiki/Universal_Transverse_Mercator_coordinate_system#/media/File:Utm-zones.jpg)

## Output Schema

### File Location

```text
data/final/final_zcta_dataset_{metro}.csv
```

### Columns

Columns are ordered logically: identifiers, affordability metrics, commute patterns, transportation modes, demographics, and transit access.

| Column | Type | Description | Source |
|--------|------|-------------|--------|
| `ZCTA5CE` | string | 5-digit ZIP Code Tabulation Area | TIGER/Line |
| `rent_to_income` | float | Median rent / median income × 100 | ACS (derived) |
| `pct_rent_burden_30` | float | % rent burdened (30%+ of income) | ACS B25070 |
| `pct_rent_burden_50` | float | % severely burdened (50%+ of income) | ACS B25070 |
| `zori` | float | Zillow Observed Rent Index ($) | Zillow |
| `commute_min_proxy` | float | Weighted avg commute time (minutes) | ACS (derived) |
| `pct_commute_lt10` | float | % commute < 10 minutes | ACS (derived) |
| `pct_commute_10_19` | float | % commute 10-19 minutes | ACS (derived) |
| `pct_commute_20_29` | float | % commute 20-29 minutes | ACS (derived) |
| `pct_commute_30_44` | float | % commute 30-44 minutes | ACS (derived) |
| `pct_commute_45_59` | float | % commute 45-59 minutes | ACS (derived) |
| `pct_commute_60_plus` | float | % commute 60+ minutes | ACS (derived) |
| `ttw_total` | int | Total workers commuting | ACS B08303 |
| `pct_drive_alone` | float | % drive alone to work | ACS B08301 |
| `pct_carpool` | float | % carpool to work | ACS B08301 |
| `pct_car` | float | % use car (alone + carpool) | ACS (derived) |
| `pct_transit` | float | % use public transit | ACS B08301 |
| `pct_walk` | float | % walk to work | ACS B08301 |
| `pct_wfh` | float | % work from home | ACS B08301 |
| `total_pop` | int | Total population | ACS B01001 |
| `pct_white` | float | % Non-Hispanic White | ACS B03002 |
| `pct_black` | float | % Non-Hispanic Black | ACS B03002 |
| `pct_asian` | float | % Non-Hispanic Asian | ACS B03002 |
| `pct_hispanic` | float | % Hispanic or Latino | ACS B03002 |
| `pct_other` | float | % Other races | ACS B03002 |
| `median_income` | float | Median household income ($) | ACS B19013 |
| `income_segment` | string | Income quartile (Low/Medium/High) | Derived |
| `stops_per_km2` | float | Transit stops per square kilometer | OSM (derived) |
| `period` | string | ZORI data month (YYYY-MM-DD) | Zillow |

### Missing Value Handling

- **Missing ZCTAs in ZORI**: `zori` = NaN (many rural ZIPs not in Zillow data)
- **Missing transit data**: `stops_per_km2` = 0 (no OSM transit data)
- **Missing ACS values**: Handled during computation (division by zero → 0)

## Troubleshooting

### Census API Issues

**Problem**: `403 Forbidden` or rate limit errors

**Solutions**:

1. Get a free API key: <https://api.census.gov/data/key_signup.html>
2. Add to `.env`: `CENSUS_API_KEY=your_key_here`
3. Verify key works: `python test_census_api.py`
4. Wait 5-10 minutes after signup for activation

**Problem**: `400 Bad Request`

**Possible Causes**:

- Invalid FIPS codes in configuration
- Requesting unavailable ACS year
- Malformed variable codes

**Debug**: Check API response in terminal output

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'src'`

**Solution**:

```bash
# Ensure you're in project root
cd /path/to/DAT490

# Verify run_pipeline.py exists in current directory
ls run_pipeline.py

# Run pipeline
python run_pipeline.py
```

### Missing Dependencies

**Problem**: `ImportError: cannot import name 'X'`

**Solution**:

```bash
pip install -r requirements.txt
```

**Common missing packages**:

- `geopandas` - Geospatial operations
- `osmnx` - OpenStreetMap queries
- `shapely` - Geometric operations
- `pyproj` - Coordinate transformations

### OSMnx / OpenStreetMap Issues

**Problem**: `ConnectionError` or timeout errors

**Causes**:

- Network connectivity issues
- Overpass API rate limiting
- OSM server downtime

**Solutions**:

1. Wait and retry (often temporary)
2. Check internet connection
3. Pipeline continues with 0 transit density on errors

**Problem**: All ZCTAs have 0 transit density

**Possible Causes**:

- Rural area with no OSM transit data (expected)
- OSM Overpass API issue
- Incorrect ZCTA geometries

**Debug**: Manually check OpenStreetMap.org for transit stops in area

### Performance Issues

**Problem**: Pipeline takes >30 minutes

**Causes**:

- Large metro with many ZCTAs (Los Angeles: ~2,500 ZCTAs)
- Slow network connection
- OSM API rate limiting

**Solutions**:

1. Run on faster internet connection
2. Pipeline automatically caches data - re-runs are faster
3. Consider processing only subset of counties (edit config)

### Output Validation

**Check pipeline output**:

```bash
# View first few rows
head -20 data/final/final_zcta_dataset_phoenix.csv

# Count ZCTAs
wc -l data/final/final_zcta_dataset_phoenix.csv

# Check for missing values
python -c "import pandas as pd; df = pd.read_csv('data/final/final_zcta_dataset_phoenix.csv'); print(df.isna().sum())"
```

**Expected missing values**:

- `zori`: 30-50% (rural ZIPs not in Zillow data)
- `stops_per_km2`: Should be 0, not NaN

## Development

### Running Tests

```bash
# Test environment setup
python test_env.py

# Test Census API connection
python test_census_api.py

# Test imports
python test_setup.py
```

### Adding New Data Sources

1. Create new module in `src/pipelines/` (e.g., `new_source.py`)
2. Implement fetch function returning DataFrame with ZCTA5CE column
3. Add function call to `build.py`
4. Add merge step in `build_final_dataset()`
5. Update output schema documentation

### Code Style

- **Docstrings**: NumPy/numpydoc style for all functions
- **Type hints**: Use for function signatures
- **Imports**: Group by standard lib, third-party, local
- **Error handling**: Raise exceptions with clear messages

### Testing Data Quality

```python
import pandas as pd

# Load output
df = pd.read_csv('data/final/final_zcta_dataset_phoenix.csv')

# Check ranges
assert df['rent_to_income'].between(0, 200).all(), "Rent-to-income out of range"
assert df['pct_hispanic'].between(0, 100).all(), "Percentages out of range"

# Check completeness
assert df['ZCTA5CE'].notna().all(), "Missing ZCTA codes"
assert df['total_pop'].gt(0).all(), "Zero population ZCTAs"

# Summary statistics
print(df.describe())
```

### Debugging Tips

1. **Enable verbose output**: Add print statements in modules
2. **Check intermediate files**: Pipeline saves debug CSVs in `data/test/`
3. **Test single metro**: Use smallest metro (Memphis) for faster iteration
4. **Use Python debugger**: `import pdb; pdb.set_trace()` in code

### Contributing

When adding features:

1. Create feature branch: `git checkout -b feature/new-feature`
2. Update this documentation
3. Add tests if applicable
4. Submit pull request with description

## Additional Resources

### Data Documentation

- [Census ACS Variables](https://api.census.gov/data/2021/acs/acs5/variables.html)
- [TIGER/Line Shapefiles](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html)
- [Zillow Research Data](https://www.zillow.com/research/data/)
- [OSMnx Documentation](https://osmnx.readthedocs.io/)

### Tools & Libraries

- [GeoPandas Documentation](https://geopandas.org/)
- [Shapely Manual](https://shapely.readthedocs.io/)
- [pandas API Reference](https://pandas.pydata.org/docs/)

### Support

- Project repository: <https://github.com/PeteVanBenthuysen/DAT490>
- Census API support: <https://www.census.gov/data/developers/guidance.html>
- Report issues: GitHub Issues

---

**Last Updated**: November 2025  
**Pipeline Version**: 1.0  
**Maintainers**: Charles Coonce
**Contact**: charlescoonce@gmail.com
