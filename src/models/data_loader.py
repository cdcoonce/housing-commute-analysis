"""
Data loading and validation utilities for DAT490 analysis.

This module handles loading ZCTA-level datasets and performing
data validation checks.
"""

import logging
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)


# Metro configuration
METRO_FILES = {
    'PHX': 'final_zcta_dataset_phoenix.csv',
    'LA': 'final_zcta_dataset_los_angeles.csv',
    'DFW': 'final_zcta_dataset_dallas.csv',
    'MEM': 'final_zcta_dataset_memphis.csv',
    'DEN': 'final_zcta_dataset_denver.csv',
    'ATL': 'final_zcta_dataset_atlanta.csv',
    'CHI': 'final_zcta_dataset_chicago.csv',
    'SEA': 'final_zcta_dataset_seattle.csv',
    'MIA': 'final_zcta_dataset_miami.csv'
}

METRO_NAMES = {
    'PHX': 'Phoenix',
    'LA': 'Los Angeles',
    'DFW': 'Dallas-Fort Worth',
    'MEM': 'Memphis',
    'DEN': 'Denver',
    'ATL': 'Atlanta',
    'CHI': 'Chicago',
    'SEA': 'Seattle',
    'MIA': 'Miami'
}


def load_and_validate_data(
    csv_path: Path,
    metro: str
) -> pl.DataFrame:
    """
    Load metro-specific ZCTA CSV and validate data quality.
    
    Performs input validation, loads CSV using Polars, checks for required columns,
    and filters rows with missing values in critical variables. Logs data quality
    metrics for transparency.
    
    Parameters
    ----------
    csv_path : Path
        Path to the CSV file containing ZCTA-level data.
    metro : str
        Metro code identifier, must be one of: PHX, LA, DFW, MEM, DEN, ATL, CHI, SEA, MIA.
    
    Returns
    -------
    pl.DataFrame
        Validated Polars DataFrame with complete cases for critical columns.
    
    Raises
    ------
    ValueError
        If metro code is not in METRO_NAMES or if critical columns are missing
        from the dataset (ZCTA5CE, rent_to_income, commute_min_proxy,
        median_income, stops_per_km2).
    FileNotFoundError
        If csv_path does not exist on the filesystem.
    
    Notes
    -----
    Critical columns are defined as those required for all research questions.
    Rows with missing values in ANY critical column are dropped and logged.
    """
    # Validate inputs before processing
    if metro not in METRO_NAMES:
        raise ValueError(f"Invalid metro code: {metro}. Must be one of {list(METRO_NAMES.keys())}")
    
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    logger.info(f"Loading data for {METRO_NAMES[metro]} from {csv_path}")
    
    # Load with polars
    df = pl.read_csv(csv_path)
    
    logger.info(f"Initial shape: {df.shape}")
    logger.info(f"Columns: {df.columns}")
    
    # Check for critical columns
    critical_cols = ['ZCTA5CE', 'rent_to_income', 'commute_min_proxy', 'median_income', 'stops_per_km2']
    missing_critical = [col for col in critical_cols if col not in df.columns]
    
    if missing_critical:
        raise ValueError(f"Missing critical columns: {missing_critical}")
    
    # Drop rows with critical nulls
    initial_count = df.shape[0]
    df = df.filter(
        pl.col('ZCTA5CE').is_not_null() &
        pl.col('rent_to_income').is_not_null() &
        pl.col('commute_min_proxy').is_not_null() &
        pl.col('median_income').is_not_null() &
        pl.col('stops_per_km2').is_not_null()
    )
    
    dropped = initial_count - df.shape[0]
    if dropped > 0:
        logger.warning(f"Dropped {dropped} rows with critical nulls")
    
    logger.info(f"Final shape after validation: {df.shape}")
    
    return df
