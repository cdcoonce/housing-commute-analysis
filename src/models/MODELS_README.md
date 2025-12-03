# DAT490 Analysis Scripts

This directory contains the analysis scripts for the DAT490 Housing-Commute Trade-Off capstone project.

## Quick Start

Run analysis for a specific metro area:

```bash
# From project root directory
python run_analysis.py --metro PHX

# Or with custom paths
python run_analysis.py \
    --metro PHX \
    --raw-dir data/final \
    --out-dir data/processed \
    --fig-dir figures
```

### Available Metro Areas

| Code | Metro Area |
|------|------------|
| `PHX` | Phoenix |
| `LA` | Los Angeles |
| `DFW` | Dallas-Fort Worth |
| `MEM` | Memphis |

## Output Structure

Running the analysis creates the following outputs:

```
data/processed/{METRO}/
  ├── cleaned_data_{metro}.csv          # Cleaned ZCTA-level data
  ├── rq1_model_data_{metro}.csv        # Model input data with predictions
  └── analysis_summary_{metro}.md       # Markdown summary tables

figures/{METRO}/
  ├── rq1_{metro}_scatter.png           # Scatter plot (commute vs rent burden)
  ├── rq1_{metro}_residuals.png         # Residual plot
  ├── rq1_{metro}_qq.png                # Q-Q plot
  └── rq1_{metro}_hist.png              # Residual histogram
```

## Module Structure

### Core Modules

- **`data_loader.py`** - Data loading and validation
- **`models.py`** - Statistical modeling utilities (OLS, cross-validation, VIF)
- **`preprocessing.py`** - Data preprocessing and feature engineering
- **`visualization.py`** - Plotting utilities
- **`reporting.py`** - Report generation utilities

### Main Script

- **`run_analysis.py`** (at project root) - Main orchestration script (CLI entry point)

### Research Question Modules

- **`rq1_housing_commute_tradeoff.py`** - RQ1: Housing-commute trade-off OLS analysis
- **`rq2_equity_analysis.py`** - RQ2: Equity analysis (optional, not yet implemented)
- **`rq3_aci_analysis.py`** - RQ3: Accessibility-Commute Index (optional, not yet implemented)

## Analysis Details

### RQ1: Housing-Commute Trade-Off

Tests whether renters in more affordable areas face longer commutes.

**Methodology:** Metro-specific linear regression with non-linearity testing

**Equation:**
```
rent_to_income = β₀ + β₁(commute) + β₂(commute²) + β₃(renter_share) + β₄(vehicle_access) + β₅(pop_density) + ε
```

**Models Tested:**
- Linear: `rent_to_income ~ commute + controls`
- Quadratic: `rent_to_income ~ commute + commute² + controls`

**Model Selection:** Best model selected via AIC (Akaike Information Criterion)

**Diagnostics:**
- Variance Inflation Factor (VIF) for multicollinearity detection
- 3-fold cross-validation (CV-RMSE)
- Heteroskedasticity-robust standard errors (HC3)

**Outputs:**
1. Model comparison table (R², AIC, CV-RMSE)
2. Selected model coefficients with robust standard errors and p-values
3. VIF diagnostics table
4. Four diagnostic plots (scatter, residuals, Q-Q, histogram)
5. Model data CSV with predictions and residuals

### Control Variables

The analysis includes the following control variables:
- `renter_share` - Percentage of renter-occupied housing units (B25003)
- `vehicle_access` - Percentage of households with 1+ vehicles (B08201)
- `pop_density` - Population density (persons per km²)

## Command Line Options

```bash
python run_analysis.py --help
```

### Required Arguments

- `--metro {PHX,LA,DFW,MEM}` - Metro area code

### Optional Arguments

- `--raw-dir PATH` - Directory containing input CSV files (default: `data/final`)
- `--out-dir PATH` - Output directory for processed data (default: `data/processed`)
- `--fig-dir PATH` - Output directory for figures (default: `figures`)
- `--zcta-shp PATH` - Path to ZCTA shapefile for choropleth maps (optional)

## Examples

### Run analysis for all metros

```bash
for metro in PHX LA DFW MEM; do
    python run_analysis.py --metro $metro
done
```

### With custom output directories

```bash
python run_analysis.py \
    --metro LA \
    --raw-dir data/final \
    --out-dir results \
    --fig-dir visualizations
```

### With shapefile for spatial analysis

```bash
python run_analysis.py \
    --metro PHX \
    --zcta-shp data/shapefiles/zcta_phoenix/zcta_phoenix.shp
```

## Requirements

- Python 3.11+
- pandas >= 2.0.0
- polars >= 0.19.0
- numpy >= 1.24.0
- statsmodels >= 0.14.0
- scikit-learn >= 1.3.0
- matplotlib >= 3.7.0
- geopandas >= 0.14.0
- shapely >= 2.0.0
- pyproj >= 3.6.0

Install dependencies:
```bash
pip install -r requirements.txt

# Or with uv
uv sync
```

## Logging

The script logs progress to console with timestamps. Log levels:
- `INFO` - Normal progress updates
- `WARNING` - Data quality issues (e.g., dropped rows)
- `ERROR` - Critical errors with diagnostic context

## Error Handling

The script includes comprehensive error handling:
- **Data validation errors** - Missing required columns, data type issues
- **File not found** - Clear messages about expected file locations
- **I/O errors** - Permission issues, disk full, etc.

All errors include diagnostic context to help troubleshoot issues.

## Development

### Adding New Research Questions

1. Create a new module: `rq{N}_description.py`
2. Implement a `run_rq{N}()` function with signature:
   ```python
   def run_rqN(df: pl.DataFrame, out_dir: Path, fig_dir: Path, metro: str) -> None:
       """Your analysis here."""
       pass
   ```
3. Import in `run_analysis.py`:
   ```python
   from rqN_description import run_rqN
   ```
4. Call in the analysis section

The script will automatically detect and run available RQ modules.

### Testing

Run with a single metro to test:
```bash
python run_analysis.py --metro PHX
```

Check outputs:
- Verify CSV files in `data/processed/PHX/`
- Verify PNG files in `figures/PHX/`
- Review `analysis_summary_phx.md` for tables and VIF diagnostics

## Troubleshooting

### "CSV file not found"
- Ensure CSV files are in `data/final/` directory
- Check filename matches expected pattern: `final_zcta_dataset_{metro}.csv`
- Files should include all 32 columns from updated pipeline

### "Dropped X rows with critical nulls"
- This is normal - ZCTAs with missing values in key variables are excluded
- Check log to see which columns had nulls

### "Missing required columns: ['renter_share', 'vehicle_access', 'pop_density']"
- Dataset is from old pipeline - use files in `data/final/` directory
- Or rebuild pipeline with: `python -m src.pipelines`

### "Module not available - skipping"
- RQ2 and RQ3 modules are optional and not yet implemented
- RQ1 will still run successfully

### Import errors
- Ensure you're running from project root directory
- Verify all dependencies are installed: `pip install -r requirements.txt` or `uv sync`
- Check that `src/models/__init__.py` exists

## Contact

For questions or issues, contact the DAT490 team.
