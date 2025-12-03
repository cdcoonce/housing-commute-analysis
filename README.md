# Housing Affordability and Commute Tradeoffs

## DAT490 Capstone Project

## Project Overview

Analyzing how commute distance and transit access influence housing affordability using data engineering and machine learning.

### Problem Statement

Quantify the relationship between housing costs, commute time, and public transit accessibility to identify affordability zones and inform policy decisions.

### Data Sources

- **Zillow**: Rental price data
- **Census ACS**: Commute patterns and demographics  
- **OpenStreetMap**: Transit network data

### Methodology

- **Data Pipeline**: Automated ETL with orchestration
- **Regression Analysis**: Multiple regression for affordability prediction
- **Clustering**: K-Means for affordability zone identification
- **Visualization**: Interactive dashboard for insights

## Project Structure

```text
DAT490/
├── run_pipeline.py           # Data pipeline entry point
├── run_analysis.py           # Analysis entry point
├── requirements.txt          # Python dependencies
├── pyproject.toml           # Project configuration
├── .env.example             # Environment variables template
├── RUNNING_PIPELINE.md      # Pipeline documentation
├── RUNNING_ANALYSIS.md      # Analysis documentation
├── data/
│   ├── raw/                 # Raw data from sources
│   ├── processed/           # Cleaned and transformed data
│   ├── final/               # Pipeline output datasets (by metro)
│   └── models/              # Trained ML models
├── src/
│   ├── pipelines/           # Data pipeline modules
│   │   ├── config.py        # Configuration & metro definitions
│   │   ├── build.py         # Main pipeline orchestration
│   │   ├── acs.py           # Census ACS data fetching
│   │   ├── demographics.py  # Demographic data processing
│   │   ├── tiger.py         # TIGER/Line geographic boundaries
│   │   ├── zori.py          # Zillow rent index data
│   │   ├── osm.py           # OpenStreetMap transit data
│   │   ├── spatial.py       # Spatial operations & joins
│   │   └── utils.py         # HTTP utilities & helpers
│   ├── models/              # Analysis modules
│   │   ├── data_loader.py   # Data loading & validation
│   │   ├── models.py        # Statistical modeling functions
│   │   ├── preprocessing.py # Data preprocessing
│   │   ├── reporting.py     # Report generation
│   │   ├── visualization.py # Plotting utilities
│   │   ├── rq1_housing_commute_tradeoff.py
│   │   ├── rq2_equity_analysis.py
│   │   └── rq3_aci_analysis.py
│   ├── dashboard/           # Interactive dashboard (WIP)
│   └── utils/               # Shared utilities
├── notebooks/               # Jupyter notebooks for EDA
├── docker/                  # Docker configuration
└── tests/                   # Unit tests
```

## Getting Started

### Prerequisites

- Python 3.9+
- Git
- Census API Key (free, recommended for pipeline)
- Docker (optional)

### Installation

```bash
# Clone repository
git clone https://github.com/PeteVanBenthuysen/DAT490.git
cd DAT490

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env and add your Census API key
# Get a free key at: https://api.census.gov/data/key_signup.html
```

## Running the Data Pipeline

The pipeline fetches and aggregates data from Census ACS, Zillow, and OpenStreetMap to create ZCTA-level datasets for housing affordability analysis.

### Quick Start

```bash
# Run pipeline for Phoenix (default)
python run_pipeline.py

# Run for specific metro area
METRO=dallas python run_pipeline.py
METRO=memphis python run_pipeline.py
METRO=los_angeles python run_pipeline.py

# Run for all metros sequentially
python run_pipeline.py --all
```

### Available Metro Areas

- **phoenix** - Phoenix-Mesa-Chandler, AZ
- **memphis** - Memphis, TN-MS-AR
- **los_angeles** - Los Angeles-Long Beach-Anaheim, CA
- **dallas** - Dallas-Fort Worth-Arlington, TX

### Pipeline Output

Output files are saved to `data/final/`:

- `final_zcta_dataset_phoenix.csv`
- `final_zcta_dataset_memphis.csv`
- `final_zcta_dataset_los_angeles.csv`
- `final_zcta_dataset_dallas.csv`

Each dataset includes:

- Rent-to-income ratios
- Commute time distributions
- Transit stop density
- Demographics (race, ethnicity, income)
- Zillow Observed Rent Index (ZORI)

**Processing time:** ~5-15 minutes per metro area

For detailed pipeline documentation, see [RUNNING_PIPELINE.md](RUNNING_PIPELINE.md)

## Running the Analysis

After running the pipeline, analyze the data for housing-commute tradeoffs:

```bash
# Run analysis for a specific metro
python run_analysis.py --metro PHX --raw-dir data/final --out-dir data/processed --fig-dir figures

# Available metro codes: PHX, LA, DFW, MEM
python run_analysis.py --metro LA --raw-dir data/final --out-dir data/processed --fig-dir figures

# Run analysis for all metros
for metro in PHX LA DFW MEM; do
    python run_analysis.py --metro $metro --raw-dir data/final --out-dir data/processed --fig-dir figures
done
```

### Analysis Output

For each metro, the analysis generates:

- Cleaned datasets in `data/processed/{METRO}/`
- Statistical models and reports
- Diagnostic plots in `figures/{METRO}/`

For detailed analysis documentation, see [RUNNING_ANALYSIS.md](RUNNING_ANALYSIS.md)

## 🐳 Docker Deployment

```bash
cd docker
docker-compose up --build
```

## Troubleshooting

### Pipeline Issues

**Census API Rate Limits:**
If you encounter rate limit errors, get a free API key:

1. Visit https://api.census.gov/data/key_signup.html
2. Add key to `.env`: `CENSUS_API_KEY=your_key_here`

**Import Errors:**
Ensure you're running from the project root directory and have activated your virtual environment.

**Missing Dependencies:**

```bash
pip install -r requirements.txt
```

**Cache Folders:**
The pipeline creates a `.cache/` folder for OSMnx data. This is normal and ignored by git.

## Deliverables

- City-level affordability map
- Interactive dashboard
- Policy recommendations
- Equity-focused analysis
- Production-ready data pipeline

## Team

DAT490 Capstone Project

## License

MIT License
