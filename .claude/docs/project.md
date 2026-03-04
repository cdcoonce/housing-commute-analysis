# Housing Affordability & Commute Trade-Off Analysis — Project Context

Data engineering and statistical analysis pipeline that quantifies the relationship between housing costs, commute time, and public transit accessibility across nine U.S. metro areas. Ingests Census ACS, Zillow ZORI, and OpenStreetMap data at the ZCTA level, then applies OLS regression, equity analysis, and a composite Affordability-Commute Index (ACI).

## Tech Stack

- **Python 3.11+** with **uv** package manager (`uv sync`, `uv run`)
- **Polars** for analysis DataFrames (`data_loader.py`, `preprocessing.py`, RQ modules)
- **pandas** + **GeoPandas** for pipeline spatial operations and Census API results
- **statsmodels** for OLS regression with HC3 robust standard errors, quantile regression
- **scikit-learn** for K-Means clustering (RQ2) and cross-validation utilities
- **matplotlib** for diagnostic plots (no seaborn unless explicitly requested)
- **OSMnx** for OpenStreetMap transit stop queries via Overpass API
- **Dash** / **Plotly** for interactive dashboard (WIP, `src/dashboard/`)
- **pytest** for testing (`uv run pytest`)
- **ruff** for linting (`uv run ruff check`)
- **hatchling** as build backend

## Project Layout

```
run_pipeline.py                 # Data pipeline CLI entry point
run_analysis.py                 # Analysis CLI entry point
pyproject.toml                  # Project config, dependencies, tool settings
.env.example                    # Environment variable template
src/
  pipelines/                    # ETL pipeline modules
    config.py                   # Metro definitions (9 metros), API keys, constants
    build.py                    # Main pipeline orchestration (8-step ETL)
    acs.py                      # Census ACS data fetching & feature computation
    demographics.py             # Race/ethnicity and income processing
    tiger.py                    # TIGER/Line boundary downloads
    zori.py                     # Zillow Observed Rent Index ingestion
    osm.py                      # OpenStreetMap transit stop density
    spatial.py                  # Spatial joins & ZCTA filtering
    utils.py                    # HTTP retry utilities
  models/                       # Statistical analysis modules
    data_loader.py              # Data loading & validation (Polars)
    preprocessing.py            # Z-scores, feature engineering, income segments
    models.py                   # OLS regression, VIF, cross-validation, ANOVA
    results.py                  # Typed dataclass containers (RQ1Results, RQ2Results, RQ3Results)
    rq1_housing_commute_tradeoff.py  # RQ1: rent ~ commute regression
    rq2_equity_analysis.py           # RQ2: equity & K-Means clustering
    rq3_aci_analysis.py              # RQ3: ACI index & quantile regression
    visualization.py            # Matplotlib diagnostic plots
    reporting.py                # Markdown table & summary generation
  dashboard/                    # Interactive dashboard (WIP)
data/
  final/                        # Pipeline output: one CSV per metro
  processed/                    # Analysis output: cleaned data & reports per metro
  raw/shapefiles/               # ZCTA shapefiles for choropleth mapping
  models/                       # Trained model artifacts
figures/                        # Diagnostic plots organized by metro
tests/                          # pytest tests + fixtures/
docs/plans/                     # Implementation plans (archive/ for completed)
```

## Test Markers

- `uv run pytest -m "not slow"` — skip slow-running tests
- `uv run pytest -m "not network"` — skip tests requiring network access (Census API, OSM)
- `uv run pytest --cov=src --cov-report=term-missing` — coverage report

## Key Architecture Patterns

- **Pipeline → Analysis separation**: `src/pipelines/` handles ETL (pandas/GeoPandas for spatial), `src/models/` handles statistics (Polars for DataFrames). The two communicate via CSV files in `data/final/`.
- **`build_final_dataset(metro_key)`** orchestrates the 8-step ETL pipeline — each step is a separate module function, making individual steps testable and re-runnable.
- **`METRO_CONFIGS` dict** in `config.py` is the single source of truth for all 9 metro area definitions (CBSA codes, counties, ZIP prefixes, UTM zones).
- **Typed result containers** (`RQ1Results`, `RQ2Results`, `RQ3Results` in `results.py`) decouple statistical computation from file I/O — analysis functions return dataclasses, orchestration writes them to disk.
- **HC3 robust standard errors** used throughout OLS regression to handle heteroscedasticity without assuming constant variance.
- **Model selection by AIC** — RQ1 compares linear vs. quadratic commute specifications, selects by Akaike Information Criterion.
- **Population-weighted aggregation** from census tracts to ZCTAs using centroid-based spatial joins.
- Coverage config omits network-dependent and integration-only modules (pipeline steps, RQ orchestration files, `run_*.py` entry points).
