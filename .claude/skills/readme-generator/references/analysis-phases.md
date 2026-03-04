# Codebase Analysis Methodology Reference

This is the detailed reference for **Step 1 (Codebase Analysis)** of the readme-generator workflow. The main SKILL.md contains a brief summary of each phase and links here for the full methodology.

This methodology is tailored for **Python** projects in **analytics engineering** and **data engineering** — the common tools include uv, Polars, Streamlit, dagster, dbt, dlt, Snowflake, openpyxl, loguru, and pytest.

Follow these four phases sequentially (unless scaling guidance says otherwise). Tag every extracted fact with a confidence level. The output of all four phases feeds directly into Step 2 (Clarifying Questions) and Step 3 (README Generation).

---

## Confidence Tracking

Tag every fact recorded during analysis. These tags propagate through the entire workflow — they determine which facts appear in the README verbatim, which require user confirmation, and which become clarifying questions.

| Tag | Meaning | Source | Downstream effect |
|---|---|---|---|
| `[confirmed]` | Read directly from source code, config file, or existing documentation | Literal value in a file | Use in README without qualification |
| `[inferred-high]` | Strong evidence from naming conventions, directory structure, or consistent patterns | Multiple corroborating signals | Use in README, but flag for user review in Step 2 |
| `[inferred-low]` | Guess based on partial or ambiguous evidence | Single weak signal, naming alone | Becomes a **clarifying question** in Step 2 |
| `[unknown]` | Cannot determine from codebase analysis alone | No evidence found | Becomes a **clarifying question** in Step 2 |

Apply tags inline next to each recorded fact:

```
- Project name: "am-external-reporting-tools" [confirmed — pyproject.toml]
- Primary purpose: Generates AM investor reports [inferred-high — module names + docstrings]
- Deployment target: Azure App Service [inferred-low — saw azure dependency but no infra config]
- Target audience: [unknown]
```

---

## Phase 1: Project Metadata Scan

**Goal:** Establish what the project is, what it depends on, and how it is configured. Answer "what is this?" without reading source code.

### Tool Actions

**1. Glob for Python project and build files — run all in parallel:**

```
**/pyproject.toml
**/setup.py
**/setup.cfg
**/requirements*.txt
**/uv.lock
```

```
**/Makefile
**/justfile
**/Taskfile.yml
```

```
**/Dockerfile
**/docker-compose.yml
**/docker-compose.yaml
```

```
**/.env.example
**/.env.template
**/.env.sample
```

**2. Glob for data engineering framework configs — run in parallel:**

```
# dagster
**/dagster.yaml
**/workspace.yaml
**/dagster_cloud.yaml
**/pyproject.toml  (look for [tool.dagster] sections)

# dbt
**/dbt_project.yml
**/profiles.yml
**/packages.yml
**/dbt_packages.yml

# dlt
**/pipeline.py
**/.dlt/config.toml
**/.dlt/secrets.toml

# Snowflake / database
**/snowflake.yml
**/database.yml
**/alembic.ini
**/alembic/env.py
```

**3. Read each found file. Extract and record:**

- Project name and version (from `pyproject.toml` `[project]` section)
- Python version constraint (e.g., `requires-python = ">=3.11"`)
- Package manager — check for `uv.lock` (uv), `poetry.lock` (poetry), `Pipfile.lock` (pipenv), or bare `requirements.txt` (pip)
- All dependencies — categorize as: **core**, **dev/test**, **optional**. For each major dependency, note its purpose:

  | Dependency | Common purpose |
  |---|---|
  | `polars` | DataFrame operations (columnar, lazy evaluation) |
  | `pandas` | DataFrame operations (row-oriented) |
  | `streamlit` | Dashboard / web UI |
  | `dagster` / `dagster-webserver` | Orchestration — asset-based data pipelines |
  | `dbt-core` / `dbt-snowflake` | SQL transformation framework |
  | `dlt` | Data loading / ingestion toolkit |
  | `snowflake-connector-python` | Snowflake warehouse connectivity |
  | `openpyxl` | Excel .xlsx/.xlsm read/write |
  | `loguru` | Structured logging (replaces stdlib logging) |
  | `msal` | Microsoft identity / Azure AD auth |
  | `httpx` / `requests` | HTTP client |
  | `pydantic` | Data validation / settings management |
  | `pyyaml` | YAML config parsing |
  | `ruff` | Linting + formatting |
  | `pytest` | Test framework |
  | `pytest-cov` | Coverage reporting |

- Available scripts/commands — check `[project.scripts]` in pyproject.toml, Makefile targets, and common uv commands (`uv run`, `uv sync`)
- Environment variables (from `.env.example` or equivalent) — classify each as **required** or **optional**

**4. Glob for configuration and toolchain files — run in parallel:**

```
**/.gitlab-ci.yml
**/.github/workflows/*.yml
**/.github/workflows/*.yaml
```

```
**/ruff.toml
**/pyproject.toml  ([tool.ruff], [tool.pytest], [tool.mypy] sections)
**/.pre-commit-config.yaml
**/mypy.ini
```

```
**/.streamlit/config.toml
```

```
**/LICENSE*
**/CLAUDE.md
**/CONTRIBUTING.md
**/CHANGELOG*
```

**5. Read CI/CD configs and toolchain configs. Record:**

- CI stages and what each stage does (lint, test, build, deploy, SAST, secret detection)
- Linting/formatting tools and their config (ruff rules, mypy strictness, pre-commit hooks)
- License type
- Any contribution guidelines that affect README content

### Phase 1 Record Template

```markdown
## Phase 1 Record — Project Metadata

| Field | Value | Confidence |
|---|---|---|
| Project name | | |
| Version | | |
| Python version | | |
| Package manager | | |
| License | | |

### Data Engineering Frameworks
| Framework | Config file | Role in project |
|---|---|---|
| | dagster.yaml / dbt_project.yml / .dlt/ / etc. | orchestration / transformation / ingestion / etc. |

### Dependencies
| Dependency | Category | Purpose |
|---|---|---|
| | core / dev / optional | |

### Scripts & Commands
| Command | What it does |
|---|---|
| `uv sync` | Install dependencies |
| `uv run streamlit run app.py` | |
| `uv run pytest` | |
| | |

### Environment Variables
| Variable | Required/Optional | Purpose |
|---|---|---|
| | | |

### CI/CD Pipeline
| Stage | Tools | What it does |
|---|---|---|
| | | |

### Toolchain
| Tool | Config file | Purpose |
|---|---|---|
| ruff | pyproject.toml | Linting + formatting |
| pytest | pyproject.toml | Testing |
| | | |
```

---

## Phase 2: Architecture Scan

**Goal:** Understand how the codebase is organized, how modules relate, and identify the dominant architecture pattern. Answer "how do the pieces fit together?"

### Tool Actions

**1. Glob for all Python source files to get the complete file tree.**

```
**/src/**/*.py
**/lib/**/*.py
**/app/**/*.py
**/*.py
```

Exclude virtual environments and build artifacts: ignore `.venv/`, `__pycache__/`, `.eggs/`, `build/`, `dist/`.

Record the directory structure with brief annotations for each directory's apparent purpose.

**2. Identify entry point(s).**

Grep for Python entry point patterns:

```
if __name__
```

Also check `pyproject.toml` for:
- `[project.scripts]` — CLI entry points
- `[project.gui-scripts]` — GUI entry points

For Streamlit apps, look for the file passed to `streamlit run` (often `app.py`, `main.py`, or `streamlit_app.py`).

For dagster projects, look for:
- `Definitions` object (dagster 1.x+) in a `definitions.py` or `__init__.py`
- `@repository` decorator (older dagster)
- `workspace.yaml` pointing to code locations

For dbt projects, the entry point is `dbt_project.yml` — models run via `dbt run`, `dbt build`, etc.

Read each entry point file. Record what it imports and what it orchestrates.

**3. Build the import graph.**

This is critical — the import graph drives the module dependency Mermaid diagram in the final README.

Grep for Python import patterns across all source files:

```
^from\s+\S+\s+import|^import\s+\S+
```

For each source file:

1. Record all **internal** imports (imports from other project modules). Ignore stdlib and third-party packages.
2. Build a directed graph: **module A -> module B** means A imports from B.
3. Identify **leaf modules** — imported by others but import nothing internal (zero outgoing edges). Common examples: `exceptions.py`, `theme.py`, `constants.py`.
4. Identify **core modules** — imported by 3+ other modules (high in-degree). Common examples: `data_transformer.py`, `models.py`, `utils.py`.
5. Identify **orchestrator modules** — import many internal modules but are imported by few (entry points, Streamlit app, dagster definitions). Common examples: `app.py`, `definitions.py`, `pipeline.py`.

**4. Identify the architecture pattern.**

Check against these data/analytics engineering patterns:

| Pattern | Indicators |
|---|---|
| **Data pipeline / ETL** | Modules named `*_transformer`, `*_loader`, `*_extractor`, `*_writer`, `*_client`; sequential data flow through stages; DataFrame-based processing (Polars/pandas); YAML config mapping data to output cells/rows |
| **dagster asset graph** | `@asset`, `@multi_asset`, `@op`, `@job`, `@schedule`, `@sensor` decorators; `Definitions` object; `dagster.yaml` / `workspace.yaml`; IO managers; resource definitions |
| **dbt project** | `models/` directory with `.sql` files; `dbt_project.yml`; `macros/`; `seeds/`; `snapshots/`; Jinja templating in SQL; `ref()` and `source()` functions |
| **dlt pipeline** | `@dlt.source`, `@dlt.resource`, `@dlt.transformer` decorators; `pipeline()` calls; `.dlt/` config directory; incremental loading patterns |
| **Streamlit dashboard** | `st.` calls throughout; sidebar/main layout; `st.cache_data`/`st.cache_resource`; session state; tab/column layout; HTML/CSS injection for styling |
| **Report generator** | Template files (Excel `.xlsm`/`.xlsx`, HTML, PDF); mapping configs; data → template population workflow; download/upload output |
| **CLI tool** | `click`, `typer`, or `argparse` usage; command/subcommand pattern; `@click.command()` / `@app.command()` decorators |
| **Library / SDK** | `__init__.py` with public API re-exports; `py.typed` marker; no entry point; extensive type annotations |

Record the matched pattern with confidence tag. Multiple patterns often apply (e.g., "Streamlit dashboard that orchestrates a data pipeline to generate reports").

**5. Grep for configuration loading patterns.**

Find runtime config files that the source code reads:

```
yaml\.safe_load|yaml\.load|json\.load|toml\.load|configparser
load_dotenv|os\.environ|os\.getenv
```

Also look for:

```
# Pydantic settings
BaseSettings|model_config
# Snowflake connection patterns
snowflake\.connector\.connect|SnowflakeClient
# loguru configuration
logger\.add|loguru
# Streamlit secrets
st\.secrets
```

Read any config files discovered (YAML, TOML, JSON) that define runtime behavior — especially `project_config.yaml`, `template_mapping.yaml`, dagster resources, dbt profiles, or dlt configs. These often contain critical domain knowledge (site names, metric mappings, column layouts, GL codes, etc.).

### Phase 2 Record Template

```markdown
## Phase 2 Record — Architecture

### Directory Structure
```
project-root/
├── src/               # [purpose]
├── config/            # [purpose]
├── templates/         # [purpose]
├── tests/             # [purpose]
└── ...
```

### Entry Points
| File | Type | What it orchestrates |
|---|---|---|
| app.py | Streamlit | Dashboard UI, data loading, report generation |
| definitions.py | dagster | Asset graph, schedules, sensors |
| dbt_project.yml | dbt | SQL model DAG |
| | | |

### Import Graph
| Source module | Imports from | What it imports (classes/functions) |
|---|---|---|
| | | |

### Module Classification
| Module | Role | In-degree | Out-degree |
|---|---|---|---|
| | core / leaf / orchestrator / intermediate | | |

### Architecture Pattern
- **Pattern:** [pattern name] [confidence]
- **Evidence:** [what indicators matched]

### Runtime Configuration
| Config file | What it controls | Loaded by |
|---|---|---|
| project_config.yaml | Site definitions, view names | snowflake_client.py |
| template_mapping.yaml | Metric → cell mappings | mapping_engine.py |
| dagster.yaml | Dagster instance config | dagster runtime |
| | | |
```

---

## Phase 3: Deep Module Analysis

**Goal:** Understand what each significant module does, its public API, and design decisions. Answer "what does each piece actually do?" Produce content for the Module Reference section and design notes.

### Module Priority Order

Analyze modules in this order:

1. **Core modules** — most imported by others (highest in-degree from Phase 2)
2. **Entry point modules** — orchestrators identified in Phase 2
3. **Largest modules** — files with the most lines of code
4. **Remaining modules** — everything else with 20+ lines of source

### Per-Module Analysis

For each significant module, Read the full file and extract:

**1. Purpose** — one sentence from module docstring or inferred from code.

**2. Key exports** — public classes, functions, constants. For each:

- Function signature with type hints
- One-line description
- Identify these common Python patterns:
  - Factory functions (e.g., `compute_financial_layout(df) -> FinancialRowLayout`)
  - Context managers (`__enter__`/`__exit__`, `@contextmanager`)
  - Frozen dataclasses / NamedTuples (especially with `__post_init__` for computed fields)
  - Pydantic models / `BaseSettings` subclasses
  - Static method classes (all methods `@staticmethod` — common in data transformers)
  - Protocol classes / ABCs
  - dagster assets (`@asset`), ops (`@op`), resources, IO managers
  - dbt macros, models (note materialization strategy)
  - dlt sources, resources, transformers

**3. Design notes** — non-obvious implementation decisions.

Grep within the module for:

```
NOTE|HACK|IMPORTANT|DESIGN|XXX|WORKAROUND|TODO|FIXME
```

Also look for these patterns common in data/analytics engineering code:

- **DataFrame conventions**: Polars vs pandas usage, lazy vs eager evaluation, column naming conventions (`Metric_Name` vs `metric_name`)
- **Metric type disambiguation**: Different source systems using different labels for the same concept (e.g., `"Actual"` vs `"Actuals"`, `"Budget"` vs `"Planned"`)
- **Aggregation modes**: `sum`, `average`, `latest`, `max` — especially when the same function supports multiple modes
- **Sign convention reversals**: Expense variance (budget - actual = favorable) vs revenue variance (actual - budget = favorable)
- **Dynamic row/column positioning**: Layout engines, row insertion/deletion, formula rewriting
- **Formula protection**: Guards preventing data writes from overwriting Excel formulas
- **Fallback/mapping logic**: GL code → category mappings, unmapped value handling, YAML fallback configs
- **Data validation**: Completeness checks, null handling, type casting, date parsing
- **Snowflake-specific patterns**: Parameterized queries (`%(param)s`), column name normalization, warehouse/role selection
- **loguru logging patterns**: `logger.bind()` for structured context, custom log levels, sink configuration
- **Caching decorators**: `@st.cache_data`, `@st.cache_resource`, `@lru_cache`, dagster `@cached_property`

**4. Internal dependencies** — what this module imports from other project modules, with specifics (which classes, functions, constants).

### End-to-End Workflow Tracing

After analyzing individual modules, trace the primary user-facing workflow through the import graph:

1. Start at the entry point (Streamlit app, dagster asset, CLI command)
2. Follow the call chain through each module
3. Record what **data structures** flow between modules:
   - `pl.DataFrame` / `pl.LazyFrame`, frozen dataclasses, `dict`, `bytes`, `io.BytesIO`, custom types
4. Label each edge of the import graph with what crosses it:
   ```
   app.py --[Config]--> SnowflakeClient --[pl.DataFrame]--> DataTransformer --[pl.DataFrame]--> MappingEngine --[list[CellMapping]]--> ExcelWriter --[BytesIO]--> download
   ```
5. Identify where data is validated, transformed, enriched, aggregated, or serialized
6. Note the **source-to-sink path**: What external system provides data? What external system receives the output?

This trace produces the **Architecture Diagram** content and the **How It Works** narrative.

### Parallel Dispatch for Large Codebases (8+ source files)

When dispatching subagents for Phase 3, use this prompt template:

```markdown
## Task: Analyze modules in [directory/cluster name]

You are analyzing a subset of Python modules for README generation. Below is the
full import graph from Phase 2 — use it to understand how your modules connect to
the rest of the system.

### Import Graph
[paste full import graph from Phase 2]

### Modules to Analyze
[list of 2-4 module file paths]

### For Each Module, Extract:
1. **Purpose** — one sentence
2. **Key exports** — public classes/functions with signatures and one-line descriptions
3. **Design notes** — non-obvious decisions, edge case handling, data conventions, aggregation modes
4. **Internal dependencies** — imports from other project modules (which names)
5. **Data flow** — what data types (pl.DataFrame, dataclasses, etc.) enter and leave this module

### Output Format
Return a filled Phase 3 Record Template for each module.

### Confidence Tags
Tag every fact: [confirmed], [inferred-high], [inferred-low], [unknown]
```

### Phase 3 Record Template

```markdown
## Phase 3 Record — Module: [module_name]

**File:** [path]
**Purpose:** [one sentence] [confidence]
**Lines:** [count]
**Role:** core / leaf / orchestrator / intermediate

### Key Exports
| Name | Kind | Signature | Description |
|---|---|---|---|
| | class / function / constant / dataclass / asset / resource | | |

### Design Notes
- [note] [confidence]

### Internal Dependencies
| Imports from | Names imported | Purpose |
|---|---|---|
| | | |

### Data Flow
- **Input:** [what data types this module receives, e.g., pl.DataFrame, dict, Config]
- **Output:** [what data types this module produces, e.g., pl.DataFrame, BytesIO, list[CellMapping]]
```

---

## Phase 4: Supporting Infrastructure Scan

**Goal:** Complete the picture with tests, error handling, templates, assets, and existing documentation.

### Tool Actions

**1. Test structure.**

Glob for test files:

```
**/test_*.py
**/*_test.py
**/tests/**/*.py
```

Glob for test configuration:

```
**/conftest.py
**/pytest.ini
**/pyproject.toml  ([tool.pytest] section)
```

Glob for fixtures:

```
**/fixtures/**/*
**/testdata/**/*
**/test_data/**/*
```

Read the first 30-50 lines of each test file to identify:

- Module under test (from imports)
- Fixtures used (function parameters matching `conftest.py` fixtures, `@pytest.fixture`, `@pytest.mark.parametrize`)
- Markers (`@pytest.mark.snowflake`, `@pytest.mark.sharepoint`, `@pytest.mark.integration`, `@pytest.mark.slow`, etc.)

Read `conftest.py` files — they define shared fixtures, markers, and test helpers that apply across test modules.

Grep for custom pytest markers across all test files:

```
pytest\.mark\.
```

Build a test-to-module mapping table.

**2. Error handling patterns.**

Grep for custom exception classes:

```
class\s+\w+(Error|Exception)\(
```

If a dedicated `exceptions.py` or `errors.py` exists, Read it fully. Record the exception hierarchy tree.

Grep for `raise` statements across source files:

```
raise\s+\w+
```

Map which modules raise which exceptions — this directly informs the Troubleshooting table.

Also grep for loguru usage patterns:

```
logger\.(error|warning|critical|exception)\(
```

These often contain user-facing error messages that belong in troubleshooting.

**3. Templates, assets, static files.**

Glob for:

```
**/templates/**/*
**/assets/**/*
**/static/**/*
**/*.xlsm
**/*.xlsx
**/*.html
**/*.css
**/*.sql
```

Note what exists and grep to find which modules reference them. Pay special attention to:

- Excel templates (`.xlsm`/`.xlsx`) — these define report structure
- SQL files — query definitions, dbt models, stored procedures
- HTML/CSS files — Streamlit styling, email templates, report templates
- YAML configs — mapping rules, site definitions, metric configurations

**4. Existing documentation.**

Glob for:

```
**/docs/**/*.md
**/*.md
**/docs/plans/**/*.md
```

Read existing docs for:

- Architecture decisions or design documents
- Implementation plans (especially in `docs/plans/`)
- API specifications
- Setup guides or runbooks

Note which docs are current vs stale (check last modified dates if available).

**5. Common error scenarios (for Troubleshooting table).**

Grep for error messages in raise statements and loguru calls:

```
raise\s+\w+\(["'].*["']\)
```

```
logger\.(error|warning)\(
```

Extract the most common/important error messages. For each, determine:

- What triggers it (missing env var, bad config, Snowflake query failure, etc.)
- What the user should do about it (check `.env`, verify config, check credentials, etc.)

Common data engineering troubleshooting categories to look for:

| Category | What to grep for |
|---|---|
| Connection failures | `ConnectionError`, `SnowflakeConnectionError`, `connect`, `authenticate` |
| Query failures | `QueryError`, `ProgrammingError`, `execute` |
| Data validation | `ValidationError`, `DataValidationError`, `validate`, `assert` |
| Missing config | `KeyError`, `environ`, `getenv`, `required` |
| Template/file errors | `FileNotFoundError`, `template`, `openpyxl` |
| Auth failures | `AuthError`, `msal`, `token`, `credential` |

### Phase 4 Record Template

```markdown
## Phase 4 Record — Supporting Infrastructure

### Test-to-Module Mapping
| Test file | Module under test | Fixtures used | Markers |
|---|---|---|---|
| | | | |

### Test Coverage Summary
- Total test files: [count]
- Custom markers: [list with purpose of each]
- conftest.py locations: [list]
- Fixture files: [list with descriptions]

### Exception Hierarchy
```
BaseError
├── ConnectionError     — [trigger]
├── QueryError          — [trigger]
├── ValidationError     — [trigger]
└── ...
```

### Templates & Assets
| Path | Type | Referenced by | Purpose |
|---|---|---|---|
| templates/*.xlsm | Excel template | excel_writer.py | Report template with formulas and VBA |
| assets/*.png | Image | app.py | Branding / UI |
| config/*.yaml | YAML config | mapping_engine.py | Metric-to-cell mappings |
| models/*.sql | dbt model | dbt runtime | SQL transformations |
| | | | |

### Existing Documentation
| File | Topic | Current/Stale |
|---|---|---|
| | | |

### Troubleshooting Scenarios
| Error message / symptom | Cause | Resolution |
|---|---|---|
| | | |
```

---

## Stop Criteria

### Stop analyzing when ALL of these are true:

- Architecture pattern confirmed with `[confirmed]` or `[inferred-high]` tag, and import graph is drawable
- Every module with 100+ lines has been Read — purpose and public API known
- Primary workflow traceable end-to-end with confirmed data types on each edge
- Source-to-sink data path documented (e.g., Snowflake → transform → Excel → download/SharePoint)
- Test-to-module mapping built
- Exception hierarchy known and at least 3 troubleshooting scenarios identified
- **OR** 60%+ context window consumed (leave room for README generation)

### Do NOT stop if any of these are true:

- Only config files have been read, not source code
- Cannot explain what the core module (highest in-degree) does
- Import graph has unresolved nodes (a module is imported but has not been analyzed)
- Found a YAML config file referenced in source code but have not read it
- Entry point identified but not yet read
- Data source connections identified but query patterns not understood

---

## Scaling Guidance

| Codebase Size | Strategy |
|---|---|
| **Small** (1-7 source files) | Execute all four phases sequentially. Read every source file fully. No parallel dispatch needed. |
| **Medium** (8-20 source files) | Phases 1-2 sequentially. Dispatch 2-3 parallel agents for Phase 3 (group modules by dependency cluster from the import graph). Phase 4 sequentially. |
| **Large** (20+ source files) | Phases 1-2 sequentially. Dispatch 4-6 parallel agents for Phase 3 (one per directory or subsystem). Dispatch 2 parallel agents for Phase 4 (one for tests, one for docs/config/assets). Merge results and verify cross-references between agent outputs. |

**When dispatching parallel agents, always include the import graph from Phase 2 in each agent's prompt.** Without it, agents cannot determine how their modules connect to the rest of the system.
