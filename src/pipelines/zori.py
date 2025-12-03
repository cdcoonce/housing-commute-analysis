"""Zillow Observed Rent Index (ZORI) data fetching and processing.

This module fetches and processes rental price data from Zillow Research.
ZORI represents a smoothed measure of typical observed market rate rent across
ZIP codes, capturing rental prices trends.
"""
from __future__ import annotations

import pandas as pd

from .utils import http_csv_to_df


def fetch_zori_latest(zori_csv_url: str) -> pd.DataFrame:
    """Fetch the latest ZORI (rent index) value for each ZIP code from Zillow.
    
    Args:
        zori_csv_url: URL to Zillow's ZORI CSV file (wide format with date columns)
        
    Returns:
        DataFrame with columns: zip (5-digit string), period (date), zori (float).
        Contains one row per ZIP code with the most recent available rent index.
        
    Raises:
        requests.HTTPError: If fetching the CSV fails
        KeyError: If expected columns are missing from the CSV
        
    Note:
        Zillow's CSV is in wide format with one column per month. This function
        converts to long format and extracts the latest non-null value per ZIP.
        Non-numeric values like 'MA' (Missing/Not Available) are handled.
    """
    # Download Zillow ZORI CSV (typically ~30-50 MB)
    zori_data = http_csv_to_df(zori_csv_url)
    
    # Standardize column name: Zillow uses 'RegionName' for ZIP codes
    if "RegionName" in zori_data.columns:
        zori_data = zori_data.rename(columns={"RegionName": "zip"})
    
    # Zero-pad ZIP codes to 5 digits (e.g., '501' → '00501')
    zori_data["zip"] = zori_data["zip"].astype(str).str.zfill(5)
    
    # Identify date columns: columns starting with year (YYYY-MM-DD or YYYY-MM)
    # Zillow format typically has columns like '2024-01-31', '2024-02-29', etc.
    date_cols = [
        col for col in zori_data.columns 
        if col[:4].isdigit() and ("-" in col or "/" in col)
    ]
    
    # Fallback: if no date pattern found, assume columns 5+ are dates
    if not date_cols:
        date_cols = zori_data.columns[5:].tolist()
    
    # Convert from wide format (one column per date) to long format (one row per date)
    zori_tidy = zori_data.melt(
        id_vars=["zip"], 
        value_vars=date_cols,
        var_name="period", 
        value_name="zori"
    )

    # DEBUG: Save intermediate tidy data for inspection
    zori_tidy.to_csv("data/test/debug_zori_tidy.csv", index=False)
    
    # Remove rows with missing ZORI values
    zori_tidy = zori_tidy.dropna(subset=["zori"])
    
    # Handle non-numeric values like 'MA' (Missing/Not Available) in Zillow data
    zori_tidy["zori"] = pd.to_numeric(zori_tidy["zori"], errors="coerce")
    zori_tidy = zori_tidy.dropna(subset=["zori"])
    
    # Keep only the most recent observation for each ZIP code
    # Sort by ZIP and period, then take the last (most recent) row per ZIP
    latest_zori = (
        zori_tidy
        .sort_values(["zip", "period"])
        .groupby("zip", as_index=False)
        .tail(1)
    )
    
    latest_zori["zori"] = latest_zori["zori"].astype(float)
    
    # Return final columns as DataFrame
    result = latest_zori[["zip", "period", "zori"]].copy()
    return result