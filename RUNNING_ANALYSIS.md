# Running the Analysis

## Quick Start

The main analysis script is now located at the project root for easier access:

```bash
# From the project root directory
python run_analysis.py --metro PHX --raw-dir data/final --out-dir data/processed --fig-dir figures
```

## Available Metro Codes

- `PHX` - Phoenix-Mesa-Chandler, AZ
- `LA` - Los Angeles-Long Beach-Anaheim, CA
- `DFW` - Dallas-Fort Worth-Arlington, TX
- `MEM` - Memphis, TN-MS-AR

## Command Options

```bash
python run_analysis.py --help
```

Options:
- `--metro` (required): Metro area code (PHX, LA, DFW, MEM)
- `--raw-dir`: Directory containing input CSV files (default: `data/raw`)
- `--out-dir`: Output directory for results (default: `data/processed`)
- `--fig-dir`: Output directory for figures (default: `figures`)
- `--zcta-shp`: Path to ZCTA shapefile for mapping (optional, auto-detected)

## Examples

### Run Phoenix Analysis
```bash
python run_analysis.py --metro PHX --raw-dir data/final --out-dir data/processed --fig-dir figures
```

### Run All Metros
```bash
for metro in PHX LA DFW MEM; do
    python run_analysis.py --metro $metro --raw-dir data/final --out-dir data/processed --fig-dir figures
done
```

### With Custom Output Locations
```bash
python run_analysis.py --metro PHX --raw-dir data/final --out-dir results/phoenix --fig-dir plots/phoenix
```

## Outputs

Each metro analysis creates:

1. **Cleaned Data**: `data/processed/{METRO}/cleaned_data_{metro}.csv`
2. **Model Results**: `data/processed/{METRO}/rq1_model_data_{metro}.csv`
3. **Analysis Report**: `data/processed/{METRO}/analysis_summary_{metro}.md`
4. **Diagnostic Plots**: `figures/{METRO}/rq1_{metro}_*.png` (4 plots)

### Key Changes:
- **Old location**: `src/models/run_analysis.py` (with relative imports)
- **New location**: `run_analysis.py` (with `src.models.*` imports)
- **Old command**: `python src/models/run_analysis.py ...`
- **New command**: `python run_analysis.py ...`

### Updated Imports in src/models/rq1_housing_commute_tradeoff.py:
Changed from:
```python
from data_loader import METRO_NAMES
from models import calculate_vif, cv_rmse, fit_ols_robust
```

To explicit relative imports:
```python
from .data_loader import METRO_NAMES
from .models import calculate_vif, cv_rmse, fit_ols_robust
```

This ensures the modules can be imported from outside the `src/models` directory.
