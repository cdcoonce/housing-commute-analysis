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

# RQ4 panel data products (design doc section 1): filename templates keyed by
# product, formatted with the metro key used in data/final/ filenames
# (e.g. "phoenix", "los_angeles" — the suffix of the METRO_FILES entries).
PANEL_FILES = {
    'zori': 'zori_panel_{metro}.csv',
    'lodes': 'lodes_panel_{metro}.csv',
    'acs2019': 'acs_commute_2019_{metro}.csv',
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

    from src.pipelines.schema import validate_final_dataset
    validate_final_dataset(df, require_all_columns=False)

    return df


def load_panel_data(
    metro: str,
    final_dir: Path
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """
    Load and validate the three RQ4 panel products for one metro.

    Reads zori_panel_<metro>.csv, lodes_panel_<metro>.csv, and
    acs_commute_2019_<metro>.csv from final_dir with ZCTA5CE pinned to Utf8
    (CSV type inference would otherwise strip leading zeros), then applies the
    corresponding pipeline schema validator to each frame.

    Parameters
    ----------
    metro : str
        Metro code identifier, must be one of: PHX, LA, DFW, MEM, DEN, ATL,
        CHI, SEA, MIA. Mapped internally to the data/final/ filename key
        (e.g. LA -> los_angeles).
    final_dir : Path
        Directory containing the committed panel CSVs (normally data/final).

    Returns
    -------
    tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]
        (zori_panel, lodes_panel, acs2019) — validated frames with Utf8
        ZCTA5CE columns.

    Raises
    ------
    ValueError
        If metro code is unknown, or any panel fails its schema validator
        (the message names the offending file and every validator error).
    FileNotFoundError
        If any of the three panel files is absent — callers (run_analysis)
        catch this to skip RQ4 on old checkouts or partial rebuilds.
    """
    if metro not in METRO_FILES:
        raise ValueError(
            f"Invalid metro code: {metro}. Must be one of {list(METRO_FILES.keys())}"
        )

    # local import mirrors load_and_validate_data (keeps schema import light)
    from src.pipelines.schema import (
        validate_acs_commute_2019,
        validate_lodes_panel,
        validate_zori_panel,
    )

    metro_key = (
        METRO_FILES[metro]
        .removeprefix('final_zcta_dataset_')
        .removesuffix('.csv')
    )
    validators = {
        'zori': validate_zori_panel,
        'lodes': validate_lodes_panel,
        'acs2019': validate_acs_commute_2019,
    }

    frames: list[pl.DataFrame] = []
    for product, template in PANEL_FILES.items():
        path = final_dir / template.format(metro=metro_key)
        if not path.exists():
            raise FileNotFoundError(f"Panel file not found: {path}")

        df = pl.read_csv(path, schema_overrides={'ZCTA5CE': pl.Utf8})
        errors = validators[product](df)
        if errors:
            raise ValueError(
                f"{path.name} failed validation: " + "; ".join(errors)
            )

        logger.info(f"Loaded {path.name}: {df.shape[0]} rows")
        frames.append(df)

    return frames[0], frames[1], frames[2]
