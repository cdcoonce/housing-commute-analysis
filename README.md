# Housing Affordability and Commute Tradeoffs

**DAT490 Capstone Project**

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
├── run_pipeline.py           # Main pipeline entry point
├── requirements.txt          # Python dependencies
├── .env.example             # Environment variables template
├── PIPELINE_README.md       # Detailed pipeline documentation
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
│   ├── models/              # ML models (regression, clustering)
│   ├── dashboard/           # Interactive dashboard
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

For detailed pipeline documentation, see [PIPELINE_README.md](PIPELINE_README.md)

## Additional Usage

```bash
# Train models (coming soon)
python -m src.models.regression
python -m src.models.clustering

# Launch dashboard (coming soon)
python -m src.dashboard.app
```

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
