# Running the Analysis

Statistical analysis of the pipeline's ZCTA datasets: RQ1 (housing-commute trade-off), RQ2 (equity), RQ3 (Affordability-Commute Index), and RQ4 (COVID and the commute gradient, when the metro's panel products are present).

## Quick Start

```bash
# Single metro
uv run python run_analysis.py --metro PHX

# All nine metros (equivalent: make analyze)
uv run python run_analysis.py --all
```

## Available Metro Codes

`PHX`, `LA`, `DFW`, `MEM`, `DEN`, `ATL`, `CHI`, `SEA`, `MIA` — see the [metro table in the README](README.md#available-metro-areas) for full names.

## Command Options

| Flag | Description | Default |
|------|-------------|---------|
| `--metro` | Metro area code (or use `--all`) | — |
| `--all` | Run analysis for all metros | — |
| `--raw-dir` | Directory containing pipeline output CSVs | `data/final` |
| `--out-dir` | Output directory for processed data and reports | `data/processed` |
| `--fig-dir` | Output directory for figures | `figures` |
| `--zcta-shp` | Path to ZCTA shapefile for choropleth maps (optional) | Auto-detected |

## Outputs

Each metro analysis creates:

1. **Cleaned data:** `data/processed/{METRO}/cleaned_data_{metro}.csv`
2. **Model data:** `data/processed/{METRO}/rq1_model_data_{metro}.csv`, `rq3_aci_data_{metro}.csv`
3. **Reports:** `data/processed/{METRO}/analysis_summary_{metro}.md` (RQ1–RQ3) and `rq4_summary_{METRO}.md` (RQ4)
4. **Figures:** `figures/{METRO}/` — RQ1 diagnostics (observed-vs-fitted scatter, residuals-vs-fitted, Q-Q, residual histogram), RQ2 boxplots and clusters, RQ3 ACI plots, RQ4 event study and gradient phases

## RQ4 Prerequisites

RQ4 needs the committed panel data products in `--raw-dir` (`zori_panel_<metro>.csv`, `lodes_panel_<metro>.csv`, `acs_commute_2019_<metro>.csv`). Build them with:

```bash
uv run python run_pipeline.py --panel --all   # or: make panel
```

If they are absent, the analysis logs a skip message and runs RQ1–RQ3 only.

See [RUNNING_PIPELINE.md](RUNNING_PIPELINE.md) for pipeline usage, panel-product details, and the revision-gate procedure. Cross-metro results live in [docs/findings.md](docs/findings.md).
