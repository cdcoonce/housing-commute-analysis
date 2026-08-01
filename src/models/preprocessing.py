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
    # Terciles divide data into 3 equal-sized groups (33.3%, 66.7% cutoffs)
    # Use drop_nulls() instead of filter() because Polars Series don't have filter method
    # (filter is a DataFrame method; drop_nulls works on both Series and DataFrame)
    income_data = df[income_col].drop_nulls()
    lower_tercile_boundary = income_data.quantile(TERCILE_LOW_QUANTILE)
    upper_tercile_boundary = income_data.quantile(TERCILE_HIGH_QUANTILE)
    
    logger.info(
        f"Income tercile boundaries: Low ≤ ${lower_tercile_boundary:,.0f}, "
        f"Medium ≤ ${upper_tercile_boundary:,.0f}, High > ${upper_tercile_boundary:,.0f}"
    )
    
    # Create categorical segments
    df = df.with_columns(
        pl.when(pl.col(income_col) <= lower_tercile_boundary).then(pl.lit('Low'))
        .when(pl.col(income_col) <= upper_tercile_boundary).then(pl.lit('Medium'))
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
