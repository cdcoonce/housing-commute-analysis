"""Visualization utilities for DAT490 analysis.

This module provides functions for creating diagnostic plots,
scatter plots, boxplots, and other visualizations.
"""

import logging
from pathlib import Path
from typing import List, Optional

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import statsmodels.api as sm

logger = logging.getLogger(__name__)


def plot_diagnostics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    resid: np.ndarray,
    x_var: np.ndarray,
    x_label: str,
    out_dir: Path,
    prefix: str,
    model_results: Optional[sm.regression.linear_model.RegressionResultsWrapper] = None,
    X_matrix: Optional[np.ndarray] = None
) -> None:
    """
    Create four diagnostic plots for OLS regression model evaluation.
    
    Generates publication-quality diagnostic plots to assess model fit,
    linearity, homoscedasticity, and normality assumptions. Saves plots
    to disk with consistent naming.
    
    Parameters
    ----------
    y_true : np.ndarray
        Observed dependent variable values (1D array).
    y_pred : np.ndarray
        Predicted values from fitted model (1D array, same length as y_true).
    resid : np.ndarray
        Residuals (y_true - y_pred, 1D array).
    x_var : np.ndarray
        Primary independent variable for scatter plot (1D array).
    x_label : str
        Label for x-axis in scatter plot (e.g., "Commute Time (minutes)").
    out_dir : Path
        Output directory for saving PNG files. Created if doesn't exist.
    prefix : str
        Filename prefix for all plots (e.g., "rq1_phx" produces "rq1_phx_scatter.png").
    model_results : statsmodels.regression.linear_model.RegressionResultsWrapper, optional
        Fitted model object for generating smooth prediction curve.
    X_matrix : np.ndarray, optional
        Full feature matrix (n_samples, n_features) used for predictions.
    
    Returns
    -------
    None
        Saves four PNG files: {prefix}_scatter.png, {prefix}_residuals.png,
        {prefix}_qq.png, {prefix}_hist.png.
    
    Raises
    ------
    ValueError
        If arrays have incompatible shapes or if out_dir cannot be created.
    
    Notes
    -----
    Generated plots:
    1. Scatter: observed vs fitted values with regression line
    2. Residual: residuals vs fitted values (check homoscedasticity)
    3. Q-Q: normal quantile-quantile plot (check normality)
    4. Histogram: residual distribution (visualize skewness/outliers)
    
    All plots saved at 300 DPI with tight bounding boxes for publication.
    """
    # Validate array shapes before plotting to fail fast
    if not (y_true.shape == y_pred.shape == resid.shape):
        raise ValueError(
            f"Array shape mismatch: y_true={y_true.shape}, y_pred={y_pred.shape}, "
            f"resid={resid.shape}. All must have same shape."
        )
    
    # Ensure output directory exists to avoid file write errors
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Scatter with fitted line
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Plot observed values as scatter
    ax.scatter(x_var, y_true, alpha=0.5, s=20, label='Observed', color='steelblue')
    
    # Generate smooth fitted curve using model predictions on regular grid
    if model_results is not None and X_matrix is not None:
        # Create smooth grid of x_var values (200 points for smooth curve)
        x_grid = np.linspace(x_var.min(), x_var.max(), 200)
        
        # Build feature matrix for grid predictions
        # Strategy: Hold all features at their mean value except x_var (commute)
        X_means = X_matrix.mean(axis=0)  # Mean of each feature column
        n_features = X_matrix.shape[1]  # Number of features (4 for linear, 5 for quadratic)
        
        # Create grid matrix: each row = [grid_commute, mean_feat2, mean_feat3, ...]
        X_grid = np.tile(X_means, (len(x_grid), 1))  # Shape: (200, n_features)
        X_grid[:, 0] = x_grid  # Replace first column (commute) with grid values
        
        # If quadratic model, update commute² column (second column)
        if n_features >= 5:  # Quadratic has 5 features: commute, commute², renter_share, vehicle, density
            X_grid[:, 1] = x_grid ** 2
        
        # Add constant term manually (prepend column of ones)
        # Using sm.add_constant() can fail if it detects constant-like patterns
        const_column = np.ones((len(x_grid), 1))
        X_grid_const = np.column_stack([const_column, X_grid])  # Shape: (200, n_features + 1)
        
        # Predict on grid to get smooth curve
        y_grid = model_results.predict(X_grid_const)
        
        # Plot smooth curve
        ax.plot(x_grid, y_grid, 'r-', linewidth=2, label='Fitted', zorder=5)
    else:
        # Fallback: Sort by x_var to create fitted line (may still be jagged)
        sort_idx = np.argsort(x_var)
        x_sorted = x_var[sort_idx]
        y_pred_sorted = y_pred[sort_idx]
        ax.plot(x_sorted, y_pred_sorted, 'r-', linewidth=2, label='Fitted', zorder=5)
    
    ax.set_xlabel(x_label)
    ax.set_ylabel('Rent-to-Income Ratio')
    ax.set_title(f'{prefix}: Fitted vs Observed')
    ax.legend(loc='best')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(out_dir / f"{prefix}_scatter.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    # 2. Residual plot
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(y_pred, resid, alpha=0.5, s=20)
    ax.axhline(y=0, color='r', linestyle='--', linewidth=2)
    ax.set_xlabel('Fitted Values')
    ax.set_ylabel('Residuals')
    ax.set_title(f'{prefix}: Residual Plot')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(out_dir / f"{prefix}_residuals.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    # 3. Q-Q plot
    # Standardize residuals so they match the theoretical normal distribution scale
    # This prevents visual compression when residuals have small variance
    standardized_resid = (resid - resid.mean()) / resid.std()
    
    fig, ax = plt.subplots(figsize=(10, 6))
    sm.qqplot(standardized_resid, line='45', ax=ax)
    ax.set_title(f'{prefix}: Q-Q Plot (Standardized Residuals)')
    ax.set_xlabel('Theoretical Quantiles')
    ax.set_ylabel('Standardized Residuals')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(out_dir / f"{prefix}_qq.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    # 4. Residual histogram
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(resid, bins=30, edgecolor='black', alpha=0.7)
    ax.axvline(x=0, color='r', linestyle='--', linewidth=2)
    ax.set_xlabel('Residuals')
    ax.set_ylabel('Frequency')
    ax.set_title(f'{prefix}: Residual Distribution')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(out_dir / f"{prefix}_hist.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    logger.info(f"Saved 4 diagnostic plots with prefix '{prefix}'")


def plot_correlation_matrix(
    df: pl.DataFrame,
    columns: List[str],
    out_path: Path,
    title: str = "Correlation Matrix"
) -> None:
    """
    Create and save a Pearson correlation matrix heatmap with diverging colormap.
    
    Visualizes pairwise correlations between continuous variables using a
    red-blue diverging colormap (RdBu_r). Useful for identifying multicollinearity
    and relationships between predictors.
    
    Parameters
    ----------
    df : pl.DataFrame
        Input DataFrame containing numeric columns.
    columns : List[str]
        Column names to include in correlation matrix. Non-existent columns
        are silently skipped with a warning.
    out_path : Path
        Output file path for PNG (e.g., "figures/correlation_matrix.png").
    title : str, default="Correlation Matrix"
        Title text displayed above heatmap.
    
    Returns
    -------
    None
        Saves correlation heatmap to out_path as PNG (300 DPI).
    
    Notes
    -----
    - Uses Pearson correlation coefficient (measures linear relationships)
    - Colormap ranges from -1 (blue, perfect negative) to +1 (red, perfect positive)
    - Silently returns if no valid columns are found (logs warning)
    """
    # Filter to available columns
    available_cols = [c for c in columns if c in df.columns]
    
    if not available_cols:
        logger.warning("No columns available for correlation matrix")
        return
    
    # Compute correlation matrix
    corr = df.select(available_cols).to_pandas().corr()
    
    # Create heatmap
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(corr, interpolation='nearest', cmap='RdBu_r', vmin=-1, vmax=1)
    
    # Set ticks and labels
    ax.set_xticks(range(len(corr.columns)))
    ax.set_yticks(range(len(corr.index)))
    ax.set_xticklabels(corr.columns, rotation=45, ha='right')
    ax.set_yticklabels(corr.index)
    
    # Add colorbar
    plt.colorbar(im, ax=ax)
    ax.set_title(title)
    
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    logger.info(f"Saved correlation matrix to {out_path}")


def plot_boxplots_by_group(
    df: pl.DataFrame,
    value_col: str,
    group_col: str,
    groups: List[str],
    out_path: Path,
    title: str,
    ylabel: str
) -> None:
    """
    Create boxplots comparing a value across groups.
    
    Args:
        df: Input DataFrame
        value_col: Column containing values to plot
        group_col: Column containing group labels
        groups: Ordered list of group names
        out_path: Output file path
        title: Plot title
        ylabel: Y-axis label
    """
    # Extract data for each group
    data = []
    for group in groups:
        group_data = df.filter(pl.col(group_col) == group)[value_col].to_numpy()
        data.append(group_data)
    
    # Create boxplot
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.boxplot(data, tick_labels=groups)
    ax.set_xlabel('Group')
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    logger.info(f"Saved boxplot to {out_path}")


def plot_scatter(
    x: np.ndarray,
    y: np.ndarray,
    out_path: Path,
    xlabel: str,
    ylabel: str,
    title: str,
    fit_line: bool = False
) -> None:
    """
    Create a scatter plot with optional fit line.
    
    Args:
        x: X values
        y: Y values
        out_path: Output file path
        xlabel: X-axis label
        ylabel: Y-axis label
        title: Plot title
        fit_line: Whether to add OLS fit line
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(x, y, s=10, alpha=0.6)
    
    if fit_line:
        # Fit simple OLS line
        X_fit = sm.add_constant(x)
        model = sm.OLS(y, X_fit).fit()
        x_range = np.linspace(np.nanmin(x), np.nanmax(x), 100)
        X_range = sm.add_constant(x_range)
        y_pred = model.predict(X_range)
        ax.plot(x_range, y_pred, 'r-', linewidth=2, label='OLS Fit')
        ax.legend()
    
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    logger.info(f"Saved scatter plot to {out_path}")
