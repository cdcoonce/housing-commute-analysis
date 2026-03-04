# Plan: Refactor Analysis Modules — Separate Logic from Reporting

**Created:** 2026-03-03
**Review Reference:** `docs/reviews/2026-03-03_full_repo_review.md`
**Estimated Effort:** ~3–4 hours total
**Priority:** MEDIUM — Improves testability, maintainability, and DRY compliance
**Depends on:** `docs/plans/quick_fixes_and_linting.md` (complete first)

---

## Scope

Each `run_rq*()` function is a monolithic 300–500 line orchestrator that:
1. Fits statistical models
2. Constructs markdown strings
3. Writes to disk
4. Generates matplotlib figures

This plan separates **analysis logic** from **reporting/IO**, making both independently testable.

Also addresses:
- §3.2: Extract shared ANOVA helper (DRY violation in `rq2_equity_analysis.py`)
- §3.3: Break long functions into smaller, focused units
- §5.3: Separate analysis results from markdown serialization

---

## Architecture: Result Dataclasses

Create a `src/models/results.py` module with typed dataclass containers for each RQ's outputs:

### Task 1: Create Result Dataclasses

**File:** `src/models/results.py` (new file)

```python
"""Typed result containers for analysis outputs.

Each dataclass captures the structured output of an RQ analysis function,
decoupling statistical computation from file I/O and report formatting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import polars as pl


@dataclass(frozen=True)
class RQ1Results:
    """Results from RQ1 housing-commute trade-off analysis.

    Attributes
    ----------
    model_linear : dict[str, Any]
        Linear model fit_ols_robust() output.
    model_quad : dict[str, Any]
        Quadratic model fit_ols_robust() output.
    best_model_name : str
        'Linear' or 'Quadratic' (selected by AIC).
    best_model : dict[str, Any]
        The selected model's fit_ols_robust() output.
    cv_rmse_linear : float
        3-fold CV-RMSE for the linear model.
    cv_rmse_quad : float
        3-fold CV-RMSE for the quadratic model.
    vif_linear : Any
        VIF DataFrame for linear model.
    vif_quad : Any
        VIF DataFrame for quadratic model.
    y_pred : np.ndarray
        Predicted values from the best model.
    residuals : np.ndarray
        Residuals from the best model.
    y_true : np.ndarray
        Observed rent_to_income values.
    commute_time : np.ndarray
        Commute time values (for plotting).
    feature_matrix : np.ndarray
        Best model's feature matrix.
    feature_names : list[str]
        Best model's feature names.
    sample_size : int
        Number of ZCTAs in the analysis.
    model_df : pl.DataFrame
        DataFrame with ZCTA IDs, actual values, predictions, and residuals.
    """

    model_linear: dict[str, Any]
    model_quad: dict[str, Any]
    best_model_name: str
    best_model: dict[str, Any]
    cv_rmse_linear: float
    cv_rmse_quad: float
    vif_linear: Any
    vif_quad: Any
    y_pred: np.ndarray
    residuals: np.ndarray
    y_true: np.ndarray
    commute_time: np.ndarray
    feature_matrix: np.ndarray
    feature_names: list[str]
    sample_size: int
    model_df: pl.DataFrame


@dataclass
class ANOVAResult:
    """Single ANOVA test result.

    Attributes
    ----------
    variable : str
        Name of the variable tested (e.g., 'Rent Burden').
    f_stat : float | None
        F-statistic, or None if test was not performed.
    p_value : float | None
        P-value, or None if test was not performed.
    """

    variable: str
    f_stat: Optional[float] = None
    p_value: Optional[float] = None

    @property
    def significant(self) -> bool:
        """Whether the ANOVA is significant at alpha=0.05."""
        return self.p_value is not None and self.p_value < 0.05


@dataclass
class RQ2Results:
    """Results from RQ2 equity analysis.

    Attributes
    ----------
    interaction_model : dict[str, Any] | None
        Interaction model output from fit_ols_robust(), or None.
    rent_by_income : pl.DataFrame | None
        Group-level rent burden statistics.
    commute_by_income : pl.DataFrame | None
        Group-level long commute statistics.
    anova_results : list[ANOVAResult]
        List of ANOVA test results for each variable tested.
    cluster_summary : pl.DataFrame | None
        K-means cluster center summary.
    cluster_labels : np.ndarray | None
        Cluster assignment per ZCTA.
    df_with_segments : pl.DataFrame
        DataFrame with income_segment and majority_race added.
    """

    interaction_model: Optional[dict[str, Any]] = None
    rent_by_income: Optional[pl.DataFrame] = None
    commute_by_income: Optional[pl.DataFrame] = None
    anova_results: list[ANOVAResult] = field(default_factory=list)
    cluster_summary: Optional[pl.DataFrame] = None
    cluster_labels: Optional[np.ndarray] = None
    df_with_segments: Optional[pl.DataFrame] = None


@dataclass
class RQ3Results:
    """Results from RQ3 ACI analysis.

    Attributes
    ----------
    aci_model : dict[str, Any] | None
        OLS model output from fit_ols_robust().
    quantile_results : dict[float, Any]
        Quantile regression results keyed by tau.
    cv_rmse_aci : float | None
        5-fold CV-RMSE for the ACI model.
    tier_summary : pl.DataFrame
        ACI tier distribution summary.
    feature_names : list[str]
        Feature names used in the ACI model.
    df_with_aci : pl.DataFrame
        DataFrame with ACI, rent_z, commute_z columns added.
    """

    aci_model: Optional[dict[str, Any]] = None
    quantile_results: dict[float, Any] = field(default_factory=dict)
    cv_rmse_aci: Optional[float] = None
    tier_summary: Optional[pl.DataFrame] = None
    feature_names: list[str] = field(default_factory=list)
    df_with_aci: Optional[pl.DataFrame] = None
```

### Verify

- `uv run python -c "from src.models.results import RQ1Results, RQ2Results, RQ3Results; print('OK')"`

---

## Task 2: Extract Shared ANOVA Helper

**Review ref:** §3.2
**Files:** `src/models/models.py` (add function), `src/models/rq2_equity_analysis.py` (use it)

### Problem

The ANOVA pattern is repeated 4 times in `rq2_equity_analysis.py` (rent burden, long commute share, transit density, rent by race). Each repetition does:
1. Filter DataFrame by group
2. Extract numpy arrays
3. Check array lengths
4. Call `f_oneway(*groups)`
5. Log the result

### Implementation

Add to `src/models/models.py`:

```python
def anova_by_group(
    df: pl.DataFrame,
    target_col: str,
    group_col: str,
    group_values: list[str],
) -> ANOVAResult:
    """Perform one-way ANOVA for a target variable grouped by a categorical column.

    Parameters
    ----------
    df : pl.DataFrame
        Input data.
    target_col : str
        Column to test (continuous variable).
    group_col : str
        Column defining groups (categorical variable).
    group_values : list[str]
        Ordered list of group labels to include.

    Returns
    -------
    ANOVAResult
        Result with f_stat and p_value, or None values if insufficient data.
    """
    from scipy.stats import f_oneway as _f_oneway

    groups = []
    for label in group_values:
        arr = (
            df.filter(pl.col(group_col) == label)[target_col]
            .drop_nulls()
            .to_numpy()
        )
        groups.append(arr)

    # Require at least 2 groups with data for ANOVA
    nonempty = [g for g in groups if len(g) > 0]
    if len(nonempty) < 2:
        logger.warning(
            f"Insufficient groups for ANOVA on {target_col} by {group_col}"
        )
        return ANOVAResult(variable=target_col)

    f_stat, p_val = _f_oneway(*nonempty)
    logger.info(f"ANOVA — {target_col} by {group_col}: F={f_stat:.3f}, p={p_val:.4f}")
    return ANOVAResult(variable=target_col, f_stat=f_stat, p_value=p_val)
```

Then replace the 4 ANOVA blocks in `rq2_equity_analysis.py` with calls to `anova_by_group()`:

```python
from .models import anova_by_group

# Instead of 15 lines per ANOVA, use:
anova_rent = anova_by_group(df, 'rent_to_income', 'income_segment', ['Low', 'Medium', 'High'])
anova_commute = anova_by_group(df, 'long45_share', 'income_segment', ['Low', 'Medium', 'High'])
anova_transit = anova_by_group(df, 'stops_per_km2', 'income_segment', ['Low', 'Medium', 'High'])
anova_race = anova_by_group(df, 'rent_to_income', 'majority_race', race_groups)
```

### Verify

- Each `anova_by_group` call produces the same F-stat/p-val as the existing inline ANOVA code
- `rq2_equity_analysis.py` shrinks by ~60 lines

---

## Task 3: Split `run_rq1()` into Analyze and Report

**Files:** `src/models/rq1_housing_commute_tradeoff.py`

### Current State

`run_rq1()` is 355 lines: ~120 lines of analysis, ~40 lines of visualization, ~195 lines of markdown writing.

### Implementation

**Step 1:** Extract analysis into `analyze_rq1()`:

```python
def analyze_rq1(df: pl.DataFrame) -> RQ1Results:
    """Perform RQ1 statistical analysis without any I/O.

    Parameters
    ----------
    df : pl.DataFrame
        Input DataFrame with required columns.

    Returns
    -------
    RQ1Results
        Typed container with all analysis outputs.
    """
    # Steps 1-7 from current run_rq1 (data prep, VIF, fit linear, fit quad, select, predict)
    ...
    return RQ1Results(...)
```

**Step 2:** Extract reporting into `report_rq1()`:

```python
def report_rq1(
    results: RQ1Results,
    out_dir: Path,
    fig_dir: Path,
    metro: str,
) -> None:
    """Write RQ1 results to markdown and generate diagnostic plots.

    Parameters
    ----------
    results : RQ1Results
        Output from analyze_rq1().
    out_dir : Path
        Markdown output directory.
    fig_dir : Path
        Figure output directory.
    metro : str
        Metro code for file naming.
    """
    # Steps 8-10 from current run_rq1 (plots, markdown, CSV)
    ...
```

**Step 3:** Rewrite `run_rq1()` as a thin orchestrator:

```python
def run_rq1(df: pl.DataFrame, out_dir: Path, fig_dir: Path, metro: str) -> None:
    """RQ1: Housing-commute trade-off analysis (full pipeline).

    Delegates to analyze_rq1() and report_rq1() for separation of concerns.
    """
    results = analyze_rq1(df)
    report_rq1(results, out_dir, fig_dir, metro)
```

### Benefits

- `analyze_rq1()` is testable with no filesystem side effects
- `report_rq1()` can be re-run without re-fitting models
- Easy to add new output formats (JSON, HTML) by writing new reporters

---

## Task 4: Split `run_rq2()` into Analyze and Report

**Files:** `src/models/rq2_equity_analysis.py`

### Current State

`run_rq2()` is 530 lines. The analysis and reporting are deeply interleaved — markdown writes happen inside conditional blocks.

### Implementation

**Step 1:** Extract analysis into `analyze_rq2()`:

```python
def analyze_rq2(df: pl.DataFrame) -> RQ2Results:
    """Perform RQ2 equity analysis without any I/O.

    Parameters
    ----------
    df : pl.DataFrame
        Input DataFrame with demographic columns.

    Returns
    -------
    RQ2Results
        Typed container with interaction model, group stats, ANOVA, clusters.
    """
    # Income segmentation, interaction model, group comparisons, ANOVA, K-means
    ...
    return RQ2Results(...)
```

**Step 2:** Extract reporting into `report_rq2()`:

```python
def report_rq2(
    results: RQ2Results,
    out_dir: Path,
    fig_dir: Path,
    metro: str,
) -> None:
    """Write RQ2 results to markdown and generate visualizations."""
    # Markdown tables, boxplots, cluster scatter, interpretation
    ...
```

**Step 3:** Extract visualization into helper functions within the module:

```python
def _plot_income_boxplots(
    df: pl.DataFrame,
    fig_dir: Path,
    metro: str,
) -> None:
    """Boxplots of rent burden and commute by income segment."""
    ...

def _plot_race_boxplots(
    df: pl.DataFrame,
    fig_dir: Path,
    metro: str,
) -> None:
    """Boxplots of rent burden by majority race."""
    ...

def _plot_clusters(
    df_cluster: pl.DataFrame,
    cluster_labels: np.ndarray,
    kmeans: KMeans,
    fig_dir: Path,
    metro: str,
) -> None:
    """Scatter plot of K-means clusters."""
    ...
```

**Step 4:** Move the ANOVA interpretation block to `report_rq2()`, consuming `RQ2Results.anova_results`.

### Verify

- `RQ2Results` captures all data needed for markdown generation
- No `open()` or `plt.savefig()` calls in `analyze_rq2()`
- Running the full pipeline produces identical markdown output

---

## Task 5: Split `run_rq3()` into Analyze and Report

**Files:** `src/models/rq3_aci_analysis.py`

### Current State

`run_rq3()` is 448 lines. Analysis (ACI computation, OLS, quantile regression) is cleaner than RQ2 but still mixed with I/O.

### Implementation

**Step 1:** Extract analysis into `analyze_rq3()`:

```python
def analyze_rq3(df: pl.DataFrame) -> RQ3Results:
    """Compute ACI and fit OLS + quantile regression models.

    Parameters
    ----------
    df : pl.DataFrame
        Input DataFrame with rent_to_income and commute_min_proxy.

    Returns
    -------
    RQ3Results
        Typed container with ACI model, quantile results, tier summary.
    """
    # ACI computation, tier classification, OLS, quantile regression
    ...
    return RQ3Results(...)
```

**Step 2:** Extract reporting into `report_rq3()`:

```python
def report_rq3(
    results: RQ3Results,
    out_dir: Path,
    fig_dir: Path,
    metro: str,
    zcta_shp: Optional[Path] = None,
) -> None:
    """Write RQ3 results to markdown and generate visualizations."""
    # Markdown, scatter, boxplots, choropleth
    ...
```

**Step 3:** Extract the choropleth into a private helper:

```python
def _plot_aci_choropleth(
    df: pl.DataFrame,
    zcta_shp: Path,
    fig_dir: Path,
    metro: str,
) -> None:
    """Generate ACI choropleth map from ZCTA shapefile."""
    ...
```

### Note on `rq3_aci_analysis.py` Docstring

The current module docstring uses Google-style `Args:` instead of NumPy-style `Parameters`. Update to match project conventions during the refactor.

---

## Task 6: Update `run_analysis.py` to Use New Structure

**File:** `run_analysis.py`

### Implementation

The existing call pattern:

```python
run_rq1(df, out_dir, fig_dir, metro)
run_rq2(df, out_dir, fig_dir, metro)
run_rq3(df, out_dir, fig_dir, metro, zcta_shp=zcta_shp)
```

This remains unchanged since `run_rq*()` still exists as the thin orchestrator. No changes needed in `run_analysis.py`.

However, the new `analyze_rq*()` functions are now available for future use cases:
- Unit testing without I/O
- Interactive notebook exploration
- Aggregating results across metros for cross-metro comparison

---

## Completion Criteria

- [ ] `src/models/results.py` exists with `RQ1Results`, `RQ2Results`, `RQ3Results`, `ANOVAResult`
- [ ] `anova_by_group()` exists in `src/models/models.py` and is used by `rq2_equity_analysis.py`
- [ ] Each `rq*` module has `analyze_rq*()` and `report_rq*()` as public functions
- [ ] `run_rq*()` is a thin wrapper calling `analyze_rq*()` → `report_rq*()` (≤ 10 lines each)
- [ ] No `open()`, `plt.savefig()`, or `write_csv()` calls exist in any `analyze_rq*()` function
- [ ] `python run_analysis.py` produces identical output to before the refactor
- [ ] `rq3_aci_analysis.py` docstring updated from Google-style to NumPy-style
- [ ] All new public functions have NumPy-style docstrings with type hints
