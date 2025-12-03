"""
Data preprocessing and feature engineering utilities.

This module handles standardization, feature transformations,
and data preparation for modeling.
"""

import logging
from typing import List, Optional

import polars as pl

logger = logging.getLogger(__name__)


# Quantile thresholds for tercile segmentation (low/medium/high)
TERCILE_LOW_QUANTILE = 0.333   # 33rd percentile boundary
TERCILE_HIGH_QUANTILE = 0.667  # 67th percentile boundary


def zscore(series: pl.Series) -> pl.Series:
    """
    Compute z-scores (standardization) for a Polars series.
    
    Transforms values to have mean=0 and std=1. Handles edge cases where
    standard deviation is zero or undefined by returning zeros.
    
    Parameters
    ----------
    series : pl.Series
        Input Polars series with numeric data.
        
    Returns
    -------
    pl.Series
        Standardized series (mean=0, std=1), or zeros if variance is zero/undefined.
    
    Notes
    -----
    Returns series of zeros (rather than NaN) when std is zero to avoid
    downstream computation errors. This occurs when all values are identical.
    """
    mu = series.mean()
    sd = series.std()
    
    # Handle edge case where std is zero or None
    if sd is None or sd == 0:
        return series * 0  # Return zeros instead of failing
    
    return (series - mu) / sd


def standardize_features(
    df: pl.DataFrame,
    features: List[str]
) -> pl.DataFrame:
    """
    Standardize continuous features using z-score transformation.
    
    Creates new columns with '_z' suffix containing standardized values (mean=0, std=1).
    Original columns are preserved unchanged. Features with zero variance are
    skipped with a warning logged.
    
    Parameters
    ----------
    df : pl.DataFrame
        Input DataFrame (not modified in-place).
    features : List[str]
        List of feature column names to standardize.
    
    Returns
    -------
    pl.DataFrame
        New DataFrame with added standardized feature columns (suffix '_z').
        Original columns remain unchanged.
    
    Raises
    ------
    ValueError
        If features list is empty.
        
    Warnings
    --------
    Logs warnings for:
    - Features not found in DataFrame (skipped)
    - Features with zero/undefined standard deviation (cannot standardize)
    
    Notes
    -----
    Standardization makes coefficients comparable across variables and
    improves numerical stability in regression. Features with zero variance
    (all values identical) cannot be standardized and are skipped.
    """
    # Validate inputs to fail fast with clear messages
    if not features:
        raise ValueError("Features list cannot be empty")
    # Work with a copy to avoid mutating input
    df_out = df.clone()
    
    for feat in features:
        if feat not in df.columns:
            logger.warning(f"Feature '{feat}' not found in DataFrame, skipping")
            continue
            
        # Calculate statistics
        mean_val = df[feat].mean()
        std_val = df[feat].std()
        
        # Only standardize if variance exists
        if std_val is None or std_val == 0:
            logger.warning(
                f"Feature '{feat}' has zero or undefined std deviation, "
                f"cannot standardize (skipping)"
            )
            continue
        
        # Create standardized column
        df_out = df_out.with_columns(
            ((pl.col(feat) - mean_val) / std_val).alias(f"{feat}_z")
        )
    
    return df_out


def create_income_segments(
    df: pl.DataFrame,
    income_col: str = 'median_income',
    segment_col: str = 'income_segment'
) -> pl.DataFrame:
    """
    Create income terciles (Low/Medium/High) based on 33rd and 67th percentiles.
    
    Divides ZCTAs into three equal-sized groups by income for equity analysis.
    Skips if income column is missing or if segment column already exists.
    
    Parameters
    ----------
    df : pl.DataFrame
        Input DataFrame containing income data.
    income_col : str, default='median_income'
        Name of column containing median household income values.
    segment_col : str, default='income_segment'
        Name for new categorical segment column to create.
        
    Returns
    -------
    pl.DataFrame
        DataFrame with new categorical column containing 'Low', 'Medium', or 'High'
        income segment labels. Original DataFrame returned unchanged if income_col
        is missing or segment_col already exists.
    
    Notes
    -----
    Tercile boundaries are computed using 33.3rd and 66.7th percentiles:
    - Low: income ≤ 33rd percentile
    - Medium: 33rd < income ≤ 67th percentile  
    - High: income > 67th percentile
    
    Null values in income_col will result in null segment values.
    """
    if income_col not in df.columns:
        logger.warning(f"Column '{income_col}' not found, cannot create segments")
        return df
    
    if segment_col in df.columns:
        logger.info(f"Column '{segment_col}' already exists, skipping creation")
        return df
    
    # Calculate tercile boundaries using standard thresholds
    # Use drop_nulls() instead of filter() because Polars Series don't have filter method
    # (filter is a DataFrame method; drop_nulls works on both Series and DataFrame)
    income_data = df[income_col].drop_nulls()
    q33 = income_data.quantile(TERCILE_LOW_QUANTILE)
    q67 = income_data.quantile(TERCILE_HIGH_QUANTILE)
    
    logger.info(f"Income tercile boundaries: Low ≤ ${q33:,.0f}, Medium ≤ ${q67:,.0f}, High > ${q67:,.0f}")
    
    # Create categorical segments
    df = df.with_columns(
        pl.when(pl.col(income_col) <= q33).then(pl.lit('Low'))
        .when(pl.col(income_col) <= q67).then(pl.lit('Medium'))
        .otherwise(pl.lit('High'))
        .alias(segment_col)
    )
    
    return df


def compute_majority_race(
    df: pl.DataFrame,
    race_cols: Optional[List[str]] = None
) -> pl.DataFrame:
    """
    Compute the majority racial/ethnic group for each ZCTA based on percentage columns.
    
    Finds the racial group with the highest percentage in each ZCTA and assigns
    it as the majority_race. Skips if fewer than 2 race columns are available.
    
    Parameters
    ----------
    df : pl.DataFrame
        Input DataFrame containing race percentage columns.
    race_cols : List[str], optional
        List of race percentage column names. If None, uses default:
        ['pct_white', 'pct_black', 'pct_hispanic', 'pct_asian'].
        
    Returns
    -------
    pl.DataFrame
        DataFrame with added 'majority_race' column containing categorical labels
        ('White', 'Black', 'Hispanic', 'Asian', or 'Other'). Returns unchanged
        if fewer than 2 race columns are available.
    
    Notes
    -----
    Null values in race columns are treated as 0.0 for comparison purposes.
    The function creates 'majority_race_idx' as an intermediate column which
    is retained for debugging purposes.
    """
    # Default race columns to standard ACS naming
    if race_cols is None:
        race_cols = ['pct_white', 'pct_black', 'pct_hispanic', 'pct_asian']
    
    # Filter to columns that actually exist in the DataFrame
    available_race_cols = [col for col in race_cols if col in df.columns]
    
    # Need at least 2 groups for meaningful majority computation
    if len(available_race_cols) < 2:
        logger.warning(
            f"Only {len(available_race_cols)} race columns found. "
            "Need at least 2 for majority race computation, skipping."
        )
        return df
    
    logger.info(f"Computing majority race using columns: {available_race_cols}")
    
    # Fill nulls with 0 to handle missing data in percentage comparisons
    race_expressions = [pl.col(col).fill_null(0.0) for col in available_race_cols]
    
    # Find index of maximum percentage
    df = df.with_columns(
        pl.concat_list(race_expressions).list.arg_max().alias('majority_race_idx')
    )
    
    # Map index to human-readable race name (title case)
    race_names = [col.replace('pct_', '').title() for col in available_race_cols]
    
    # Build conditional expression for mapping indices to names
    majority_expr = pl.lit('Other')  # Default if all are null or tied
    for idx, name in enumerate(race_names):
        majority_expr = (
            pl.when(pl.col('majority_race_idx') == idx)
            .then(pl.lit(name))
            .otherwise(majority_expr)
        )
    
    df = df.with_columns(majority_expr.alias('majority_race'))
    
    logger.info(
        f"Majority race distribution:\n{df['majority_race'].value_counts().sort('majority_race')}"
    )
    
    return df
