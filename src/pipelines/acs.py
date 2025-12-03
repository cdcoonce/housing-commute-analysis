"""American Community Survey (ACS) data fetching and feature engineering.

This module retrieves tract-level demographic and economic data from the Census API
and computes derived features for housing affordability and commute analysis.
Supports both current (2021) and historical data extraction (2015, 2017, 2019).
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import requests

from .config import CENSUS_API_KEY

# Census API configuration - default to latest available
DEFAULT_ACS_YEAR = 2021  # Latest with full API support
ACS_DATASET = "acs/acs5"  # 5-year estimates for stable tract-level data

# Available historical years for panel analysis
AVAILABLE_ACS_YEARS = [2015, 2017, 2019, 2021, 2023]

# Mapping of feature names to Census variable codes
ACS_VARS = {
    "median_rent": "B25064_001E",  # Median gross rent
    "median_income": "B19013_001E",  # Median household income
    # Travel time to work - complete distribution (B08303)
    "ttw_total": "B08303_001E",  # Total workers for travel time calculation
    "ttw_lt5": "B08303_002E",  # Less than 5 minutes
    "ttw_5_9": "B08303_003E",  # 5 to 9 minutes
    "ttw_10_14": "B08303_004E",  # 10 to 14 minutes
    "ttw_15_19": "B08303_005E",  # 15 to 19 minutes
    "ttw_20_24": "B08303_006E",  # 20 to 24 minutes
    "ttw_25_29": "B08303_007E",  # 25 to 29 minutes
    "ttw_30_34": "B08303_008E",  # 30 to 34 minutes
    "ttw_35_39": "B08303_009E",  # 35 to 39 minutes
    "ttw_40_44": "B08303_010E",  # 40 to 44 minutes
    "ttw_45_59": "B08303_011E",  # 45 to 59 minutes
    "ttw_60_89": "B08303_012E",  # 60 to 89 minutes
    "ttw_90_plus": "B08303_013E",  # 90 or more minutes
    # Transportation mode to work (B08301)
    "mode_total": "B08301_001E",  # Total workers (universe for mode share)
    "mode_car_alone": "B08301_003E",  # Car, truck, or van - drove alone
    "mode_carpool": "B08301_004E",  # Car, truck, or van - carpooled
    "mode_transit": "B08301_010E",  # Public transportation (excluding taxicab)
    "mode_walk": "B08301_019E",  # Walked
    "mode_other": "B08301_020E",  # Taxicab, motorcycle, bicycle, or other means
    "mode_wfh": "B08301_021E",  # Worked from home
    # Rent burden (B25070 - Gross Rent as a Percentage of Household Income)
    "rent_burden_total": "B25070_001E",  # Total renter households (universe)
    "rent_burden_30_34": "B25070_008E",  # 30.0 to 34.9 percent
    "rent_burden_35_39": "B25070_009E",  # 35.0 to 39.9 percent
    "rent_burden_40_49": "B25070_010E",  # 40.0 to 49.9 percent
    "rent_burden_50_plus": "B25070_011E",  # 50.0 percent or more
    # Tenure (B25003 - Tenure)
    "tenure_total": "B25003_001E",  # Total occupied housing units
    "tenure_owner": "B25003_002E",  # Owner occupied
    "tenure_renter": "B25003_003E",  # Renter occupied
    # Vehicle availability (B08201 - Household Size by Vehicles Available)
    "vehicles_total": "B08201_001E",  # Total households (universe for vehicle calculation)
    "vehicles_none": "B08201_002E",  # No vehicle available
    "vehicles_1": "B08201_003E",  # 1 vehicle available
    "vehicles_2_plus": "B08201_007E",  # 2 or more vehicles available (sum of B08201_007-013)
}


def fetch_acs_for_county(
    state_fips: str, 
    county_fips: str, 
    year: int = DEFAULT_ACS_YEAR,
    api_key: Optional[str] = CENSUS_API_KEY
) -> pd.DataFrame:
    """Fetch American Community Survey data for all census tracts in a county.
    
    Args:
        state_fips: Two-digit FIPS code for the state (e.g., '04' for Arizona)
        county_fips: Three-digit FIPS code for the county (e.g., '013' for Maricopa)
        year: ACS year to fetch (2015, 2017, 2019, or 2021). Defaults to 2021.
        api_key: Census API key for higher rate limits (optional but recommended)
    
    Returns:
        DataFrame with columns: GEOID, year, median_rent, median_income, ttw_total,
        ttw_45_59, ttw_60_89, ttw_90_plus, mode variables (B08301), and rent burden
        variables (B25070). One row per census tract.
        
    Raises:
        ValueError: If state_fips, county_fips, or year are invalid
        requests.HTTPError: If the Census API request fails
        
    Note:
        GEOID is an 11-digit code: 2-digit state + 3-digit county + 6-digit tract
        Year parameter enables historical data extraction for panel analysis.
    """
    # Validate input FIPS codes
    if not state_fips or not state_fips.isdigit() or len(state_fips) != 2:
        raise ValueError(f"Invalid state FIPS code: {state_fips}. "
                        "Must be 2-digit numeric string (e.g., '04').")
    
    if not county_fips or not county_fips.isdigit() or len(county_fips) != 3:
        raise ValueError(f"Invalid county FIPS code: {county_fips}. "
                        "Must be 3-digit numeric string (e.g., '013').")
    
    if year not in AVAILABLE_ACS_YEARS:
        raise ValueError(f"Invalid ACS year: {year}. "
                        f"Must be one of {AVAILABLE_ACS_YEARS}")
    
    url = f"https://api.census.gov/data/{year}/{ACS_DATASET}"
    variable_codes = ",".join(ACS_VARS.values())
    params = {
        "get": variable_codes,
        "for": "tract:*",  # Request all tracts
        "in": f"state:{state_fips}+county:{county_fips}"
    }
    if api_key:
        params["key"] = api_key
    
    # Fetch data from Census API (120s timeout for large counties)
    response = requests.get(url, params=params, timeout=120)
    response.raise_for_status()
    
    # Parse JSON response: first row is header, rest are data
    json_data = response.json()
    header, data_rows = json_data[0], json_data[1:]
    
    # Convert to DataFrame and rename columns to human-readable names
    acs_data = pd.DataFrame(data_rows, columns=header)
    rename_map = {api_code: feature_name for feature_name, api_code in ACS_VARS.items()}
    acs_data = acs_data.rename(columns=rename_map)
    
    # Zero-pad FIPS codes to standard lengths for consistent string concatenation
    acs_data["state"] = acs_data["state"].astype(str).str.zfill(2)
    acs_data["county"] = acs_data["county"].astype(str).str.zfill(3)
    acs_data["tract"] = acs_data["tract"].astype(str).str.zfill(6)
    
    # Create standard 11-digit GEOID identifier
    acs_data["GEOID"] = (
        acs_data["state"] + acs_data["county"] + acs_data["tract"]
    ).astype(str)
    
    # Convert numeric columns, handling Census null codes (negative values like -666666666)
    # errors="coerce" converts invalid/null values to NaN for downstream handling
    numeric_cols = ["median_rent", "median_income", "ttw_total", 
                    "ttw_lt5", "ttw_5_9", "ttw_10_14", "ttw_15_19", "ttw_20_24",
                    "ttw_25_29", "ttw_30_34", "ttw_35_39", "ttw_40_44",
                    "ttw_45_59", "ttw_60_89", "ttw_90_plus",
                    "mode_total", "mode_car_alone", "mode_carpool", "mode_transit",
                    "mode_walk", "mode_other", "mode_wfh",
                    "rent_burden_total", "rent_burden_30_34", "rent_burden_35_39",
                    "rent_burden_40_49", "rent_burden_50_plus",
                    "tenure_total", "tenure_owner", "tenure_renter",
                    "vehicles_total", "vehicles_none", "vehicles_1", "vehicles_2_plus"]
    for col in numeric_cols:
        acs_data[col] = pd.to_numeric(acs_data[col], errors="coerce")
    
    # Add year column for panel data tracking
    acs_data["year"] = year
    
    # Select and return final columns as DataFrame
    result_cols = ["GEOID", "year"] + numeric_cols
    return acs_data[result_cols].copy()

def compute_acs_features(acs_df: pd.DataFrame) -> pd.DataFrame:
    """Compute derived features from raw ACS data for housing and commute analysis.
    
    Args:
        acs_df: DataFrame from fetch_acs_for_county() with GEOID and ACS variables
        
    Returns:
        DataFrame with original columns plus computed features:
        - rent_to_income: Monthly rent as a fraction of monthly income (0-1 range)
        - commute_min_proxy: Estimated average commute time in minutes
        - pct_commute_lt10: Percentage with commute < 10 minutes
        - pct_commute_10_19: Percentage with commute 10-19 minutes
        - pct_commute_20_29: Percentage with commute 20-29 minutes
        - pct_commute_30_44: Percentage with commute 30-44 minutes
        - pct_commute_45_59: Percentage with commute 45-59 minutes
        - pct_commute_60_plus: Percentage with commute 60+ minutes
        - pct_drive_alone: Percentage driving alone to work
        - pct_carpool: Percentage carpooling to work
        - pct_transit: Percentage using public transit to work
        - pct_walk: Percentage walking to work
        - pct_wfh: Percentage working from home
        - pct_car: Percentage using car (alone + carpool)
        - pct_rent_burden_30: Percentage of renters paying 30%+ of income on rent
        - pct_rent_burden_50: Percentage of renters paying 50%+ of income on rent
        - renter_share: Percentage of occupied housing units that are renter-occupied
        - pct_no_vehicle: Percentage of households with no vehicle available
        - vehicle_access: Percentage of households with 1+ vehicles available
        - long45_share: [DEPRECATED] Use (pct_commute_45_59 + pct_commute_60_plus) / 100
        - long60_share: [DEPRECATED] Use pct_commute_60_plus / 100
        
    Note:
        Census uses negative values (e.g., -666666666) to indicate missing data.
        These are converted to pd.NA. Division by zero returns pd.NA.
    """
    features = acs_df.copy()
    
    # Replace Census null codes (negative values) with NA
    numeric_cols = ["median_rent", "median_income", "ttw_total",
                    "ttw_lt5", "ttw_5_9", "ttw_10_14", "ttw_15_19", "ttw_20_24",
                    "ttw_25_29", "ttw_30_34", "ttw_35_39", "ttw_40_44",
                    "ttw_45_59", "ttw_60_89", "ttw_90_plus",
                    "mode_total", "mode_car_alone", "mode_carpool", "mode_transit",
                    "mode_walk", "mode_other", "mode_wfh",
                    "rent_burden_total", "rent_burden_30_34", "rent_burden_35_39",
                    "rent_burden_40_49", "rent_burden_50_plus",
                    "tenure_total", "tenure_owner", "tenure_renter",
                    "vehicles_total", "vehicles_none", "vehicles_1", "vehicles_2_plus"]
    for col in numeric_cols:
        features.loc[features[col] < 0, col] = pd.NA
    
    # Compute rent-to-income ratio (monthly rent / monthly income)
    # Only calculate where both values are positive and valid
    features["rent_to_income"] = pd.NA
    valid_income_rent = (features["median_income"] > 0) & (features["median_rent"] > 0)
    features.loc[valid_income_rent, "rent_to_income"] = (
        features.loc[valid_income_rent, "median_rent"] / 
        (features.loc[valid_income_rent, "median_income"] / 12.0)
    )
    
    # Avoid division by zero in commute calculations
    # Replace 0 with NA so divisions propagate NA instead of raising errors or returning inf
    total_workers = features["ttw_total"].replace(0, pd.NA)
    
    # Share of workers by commute time categories (as percentages 0-100)
    features["pct_commute_lt10"] = (features["ttw_lt5"] + features["ttw_5_9"]) / total_workers * 100
    features["pct_commute_10_19"] = (features["ttw_10_14"] + features["ttw_15_19"]) / total_workers * 100
    features["pct_commute_20_29"] = (features["ttw_20_24"] + features["ttw_25_29"]) / total_workers * 100
    features["pct_commute_30_44"] = (features["ttw_30_34"] + features["ttw_35_39"] + features["ttw_40_44"]) / total_workers * 100
    features["pct_commute_45_59"] = (features["ttw_45_59"]) / total_workers * 100
    features["pct_commute_60_plus"] = (features["ttw_60_89"] + features["ttw_90_plus"]) / total_workers * 100
    
    # Legacy aliases for backward compatibility (if needed in existing code)
    features["long45_share"] = (features["pct_commute_45_59"] + features["pct_commute_60_plus"]) / 100
    features["long60_share"] = features["pct_commute_60_plus"] / 100
    
    # Estimated average commute time using midpoints of all bins:
    # <5→2.5, 5-9→7, 10-14→12, 15-19→17, 20-24→22, 25-29→27, 30-34→32, 35-39→37, 40-44→42
    # 45-59→52, 60-89→75, 90+→100 (conservative estimate)
    features["commute_min_proxy"] = (
        (features["ttw_lt5"] * 2.5) +
        (features["ttw_5_9"] * 7) +
        (features["ttw_10_14"] * 12) +
        (features["ttw_15_19"] * 17) +
        (features["ttw_20_24"] * 22) +
        (features["ttw_25_29"] * 27) +
        (features["ttw_30_34"] * 32) +
        (features["ttw_35_39"] * 37) +
        (features["ttw_40_44"] * 42) +
        (features["ttw_45_59"] * 52) + 
        (features["ttw_60_89"] * 75) + 
        (features["ttw_90_plus"] * 100)
    ) / total_workers
    
    # Transportation mode shares (avoid division by zero)
    mode_total = features["mode_total"].replace(0, pd.NA)
    
    features["pct_drive_alone"] = (features["mode_car_alone"] / mode_total) * 100
    features["pct_carpool"] = (features["mode_carpool"] / mode_total) * 100
    features["pct_transit"] = (features["mode_transit"] / mode_total) * 100
    features["pct_walk"] = (features["mode_walk"] / mode_total) * 100
    features["pct_wfh"] = (features["mode_wfh"] / mode_total) * 100
    
    # Combined car usage (drive alone + carpool)
    features["pct_car"] = features["pct_drive_alone"] + features["pct_carpool"]
    
    # Rent burden categories (avoid division by zero)
    rent_burden_total = features["rent_burden_total"].replace(0, pd.NA)
    
    # Rent burdened: 30%+ of income on rent
    features["pct_rent_burden_30"] = (
        (features["rent_burden_30_34"] + features["rent_burden_35_39"] + 
         features["rent_burden_40_49"] + features["rent_burden_50_plus"]) / 
        rent_burden_total
    ) * 100
    
    # Severely rent burdened: 50%+ of income on rent
    features["pct_rent_burden_50"] = (
        features["rent_burden_50_plus"] / rent_burden_total
    ) * 100
    
    # Renter share (percentage of occupied units that are renter-occupied)
    tenure_total = features["tenure_total"].replace(0, pd.NA)
    features["renter_share"] = (features["tenure_renter"] / tenure_total) * 100
    
    # Vehicle availability (percentage of households with no vehicle)
    # Higher values indicate lower vehicle access
    vehicles_total = features["vehicles_total"].replace(0, pd.NA)
    features["pct_no_vehicle"] = (features["vehicles_none"] / vehicles_total) * 100
    
    # Inverse measure: vehicle access (percentage with 1+ vehicles)
    features["vehicle_access"] = ((features["vehicles_1"] + features["vehicles_2_plus"]) / 
                                   vehicles_total) * 100
    
    return features