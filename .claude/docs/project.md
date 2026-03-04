# AM External Reporting Tools — Project Context

Streamlit web app that generates monthly project performance reports for Clearway Energy asset managers. Queries Snowflake, transforms data with Polars, and populates a branded Excel `.xlsm` template with optional SharePoint upload.

## Tech Stack

- **Python 3.11+** with **uv** package manager (`uv sync`, `uv run`)
- **Polars** for DataFrames (not pandas)
- **Streamlit** for the dashboard UI
- **openpyxl** for Excel template manipulation
- **pytest** for testing (`uv run pytest`)
- **ruff** for linting (`uv run ruff check`)
- **GitLab CI** for CI/CD (SAST + secret detection)

## Project Layout

```
app.py                          # Streamlit entry point
src/                            # Core modules
config/                         # project_config.yaml, template_mapping.yaml
templates/                      # Excel .xlsm templates
tests/                          # pytest tests + fixtures/ CSV data
docs/plans/                     # Implementation plans and design documents
```

## Test Markers

- `uv run pytest -m "not snowflake"` — skip live Snowflake tests
- `uv run pytest -m "not sharepoint"` — skip live SharePoint tests

## Key Architecture Patterns

- **RowLayoutEngine** is the single source of truth for Financial Summary row positions — all row numbers are computed dynamically from offtaker counts, never hardcoded
- **MappingEngine** resolves metric values to Excel cells via `template_mapping.yaml` — supports both dynamic (layout-aware) and legacy (YAML hardcoded) paths
- **ExcelWriter** adjusts rows bottom-to-top so inserts/deletes in lower sections don't shift upper sections
- Revenue categories support dynamic offtaker sub-rows; expense metrics marked `derived: true` are computed in Python (e.g., Other Expenses = Operating Expense minus 6 line items)
- Settlement data uses `Category` + `Product_Type` filters; budget data uses GL codes mapped to settlement categories via `build_gl_to_category_map()`
