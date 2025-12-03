"""Demographic data fetching and processing from Census ACS.

This module fetches race, ethnicity, and income data from the American Community
Survey and processes it to create demographic composition metrics at the tract level,
suitable for equity analysis and demographic segmentation.
"""
from __future__ import annotations

import pandas as pd

from .config import CENSUS_API_KEY
from .utils import http_json_to_dict


def fetch_demographics_for_county(
    state_fips: str, 
    county_fips: str,
    year: int = 2023
) -> pd.DataFrame:
    """Fetch demographic data (race, ethnicity, income) from ACS for a single county.
    
    Retrieves data from multiple ACS tables:
    - B03002: Hispanic or Latino Origin by Race (for ethnicity breakdown)
    - B02001: Race Alone (for detailed race categories)
    - B19013: Median Household Income
    
    Args:
        state_fips: 2-digit state FIPS code (e.g., '04' for Arizona)
        county_fips: 3-digit county FIPS code (e.g., '013' for Maricopa)
        year: ACS year to fetch (2015, 2017, 2019, or 2021). Defaults to 2021.
        
    Returns:
        DataFrame with one row per census tract containing:
        - GEOID: 11-digit tract identifier (state+county+tract)
        - year: ACS year
        - total_pop: Total population
        - hispanic: Hispanic/Latino population (any race)
        - white_nh: White alone, not Hispanic
        - black_nh: Black/African American alone, not Hispanic
        - asian_nh: Asian alone, not Hispanic
        - other_nh: Other races (including multiracial), not Hispanic
        - median_income: Median household income in past 12 months
        
    Raises:
        requests.HTTPError: If Census API request fails
        ValueError: If state_fips, county_fips, or year format is invalid
        
    Note:
        Census table variable codes:
        - B03002_001E: Total population (universe)
        - B03002_012E: Hispanic or Latino (any race)
        - B03002_003E: White alone, not Hispanic/Latino
        - B03002_004E: Black/African American alone, not Hispanic/Latino
        - B03002_006E: Asian alone, not Hispanic/Latino
        - B02001_001E: Total population (for validation)
        - B19013_001E: Median household income
    """
    # Validate FIPS code format
    if not (state_fips.isdigit() and len(state_fips) == 2):
        raise ValueError(f"Invalid state_fips: {state_fips}. Must be 2-digit string.")
    if not (county_fips.isdigit() and len(county_fips) == 3):
        raise ValueError(f"Invalid county_fips: {county_fips}. Must be 3-digit string.")
    
    # Validate year
    available_years = [2015, 2017, 2019, 2021, 2023]
    if year not in available_years:
        raise ValueError(f"Invalid year: {year}. Must be one of {available_years}")
    
    # ACS 5-year estimates endpoint (year-specific)
    base_url = f"https://api.census.gov/data/{year}/acs/acs5"
    
    # Define variables to fetch
    variables = [
        "B03002_001E",  # Total population
        "B03002_012E",  # Hispanic or Latino (any race)
        "B03002_003E",  # White alone, not Hispanic/Latino
        "B03002_004E",  # Black/African American alone, not Hispanic/Latino
        "B03002_006E",  # Asian alone, not Hispanic/Latino
        "B19013_001E",  # Median household income
    ]
    
    # Build query parameters
    params = {
        "get": ",".join(variables),
        "for": f"tract:*",
        "in": f"state:{state_fips} county:{county_fips}",
    }
    
    # Add API key if available (higher rate limits)
    if CENSUS_API_KEY:
        params["key"] = CENSUS_API_KEY
    
    # Fetch data from Census API
    response_data = http_json_to_dict(base_url, params)
    
    # Convert to DataFrame
    # First row is header, remaining rows are data
    header = response_data[0]
    rows = response_data[1:]
    demographics_raw = pd.DataFrame(rows, columns=header)
    
    # Build GEOID: state (2) + county (3) + tract (6)
    demographics_raw["GEOID"] = (
        demographics_raw["state"] + 
        demographics_raw["county"] + 
        demographics_raw["tract"]
    )
    
    # Rename columns to descriptive names
    demographics_raw = demographics_raw.rename(columns={
        "B03002_001E": "total_pop",
        "B03002_012E": "hispanic",
        "B03002_003E": "white_nh",
        "B03002_004E": "black_nh",
        "B03002_006E": "asian_nh",
        "B19013_001E": "median_income",
    })
    
    # Convert to numeric (Census API returns strings)
    numeric_cols = ["total_pop", "hispanic", "white_nh", "black_nh", "asian_nh", "median_income"]
    for col in numeric_cols:
        demographics_raw[col] = pd.to_numeric(demographics_raw[col], errors="coerce")
    
    # Calculate "other" category (residual: total - hispanic - white_nh - black_nh - asian_nh)
    # This captures: Native American, Pacific Islander, Other, Two or more races (all non-Hispanic)
    demographics_raw["other_nh"] = (
        demographics_raw["total_pop"] - 
        demographics_raw["hispanic"] - 
        demographics_raw["white_nh"] - 
        demographics_raw["black_nh"] - 
        demographics_raw["asian_nh"]
    ).clip(lower=0)  # Ensure non-negative due to potential rounding
    
    # Add year column for panel data tracking
    demographics_raw["year"] = year
    
    # Select final columns
    final_cols = [
        "GEOID", "year", "total_pop", "hispanic", "white_nh", "black_nh", 
        "asian_nh", "other_nh", "median_income"
    ]
    
    return demographics_raw[final_cols].copy()


def compute_demographic_percentages(demographics_df: pd.DataFrame) -> pd.DataFrame:
    """Convert demographic counts to percentages at tract level.
    
    Args:
        demographics_df: DataFrame from fetch_demographics_for_county() with counts
        
    Returns:
        DataFrame with additional percentage columns:
        - pct_hispanic, pct_white, pct_black, pct_asian, pct_other (all 0-100 scale)
        - Retains original count columns and median_income
        
    Note:
        Percentages are calculated as (group_count / total_pop) * 100
        Tracts with zero population get 0% for all groups
    """
    result = demographics_df.copy()
    
    # Calculate percentages (handle division by zero with fillna)
    result["pct_hispanic"] = (result["hispanic"] / result["total_pop"] * 100).fillna(0)
    result["pct_white"] = (result["white_nh"] / result["total_pop"] * 100).fillna(0)
    result["pct_black"] = (result["black_nh"] / result["total_pop"] * 100).fillna(0)
    result["pct_asian"] = (result["asian_nh"] / result["total_pop"] * 100).fillna(0)
    result["pct_other"] = (result["other_nh"] / result["total_pop"] * 100).fillna(0)
    
    return result


def aggregate_demographics_to_zcta(
    demographics_df: pd.DataFrame,
    tract_to_zcta_map: pd.DataFrame
) -> pd.DataFrame:
    """Aggregate tract-level demographics to ZCTA level.
    
    Uses population-weighted averaging for percentages and median income.
    
    Args:
        demographics_df: Tract-level demographics with percentages
        tract_to_zcta_map: Mapping of GEOID to ZCTA5CE from spatial join
        
    Returns:
        DataFrame with one row per ZCTA containing:
        - ZCTA5CE: ZIP code tabulation area identifier
        - total_pop: Sum of population across tracts
        - pct_hispanic, pct_white, pct_black, pct_asian, pct_other: 
          Population-weighted average percentages
        - median_income: Population-weighted average income
        
    Note:
        Population-weighted averaging ensures larger tracts have proportional
        influence on ZCTA-level percentages. Formula:
        weighted_pct = sum(pct_i * pop_i) / sum(pop_i)
    """
    # Join demographics with tract-to-ZCTA mapping
    demo_with_zcta = demographics_df.merge(tract_to_zcta_map, on="GEOID", how="inner")
    
    # For each ZCTA, calculate population-weighted averages
    # Population weighting ensures larger tracts contribute proportionally to ZCTA metrics,
    # avoiding bias from small-population tracts with extreme values
    def weighted_mean(group: pd.DataFrame, value_col: str) -> float:
        """Calculate population-weighted mean: sum(value_i * pop_i) / sum(pop_i)."""
        weights = group["total_pop"]
        values = group[value_col]
        # Return 0 if total population is 0 to avoid division by zero
        return (values * weights).sum() / weights.sum() if weights.sum() > 0 else 0
    
    # Group by ZCTA and aggregate
    zcta_demographics = demo_with_zcta.groupby("ZCTA5CE").apply(
        lambda group: pd.Series({
            "total_pop": group["total_pop"].sum(),
            "pct_hispanic": weighted_mean(group, "pct_hispanic"),
            "pct_white": weighted_mean(group, "pct_white"),
            "pct_black": weighted_mean(group, "pct_black"),
            "pct_asian": weighted_mean(group, "pct_asian"),
            "pct_other": weighted_mean(group, "pct_other"),
            "median_income": weighted_mean(group, "median_income"),
        }),
        include_groups=False
    ).reset_index()
    
    return zcta_demographics


def create_income_segments(zcta_df: pd.DataFrame) -> pd.DataFrame:
    """Add income_segment categorical variable based on quartiles.
    
    Segments ZCTAs into three income categories using quartile cutoffs:
    - "Low": Bottom 25% (below 25th percentile)
    - "Medium": Middle 50% (25th to 75th percentile)
    - "High": Top 25% (above 75th percentile)
    
    Args:
        zcta_df: DataFrame with median_income column
        
    Returns:
        DataFrame with added income_segment column (categorical)
        
    Note:
        ZCTAs with null median_income values will have null income_segment
    """
    result = zcta_df.copy()
    
    # Calculate quartiles (excluding null values)
    q25 = result["median_income"].quantile(0.25)
    q75 = result["median_income"].quantile(0.75)
    
    # Create categorical segments
    def assign_segment(income):
        if pd.isna(income):
            return None
        elif income < q25:
            return "Low"
        elif income <= q75:
            return "Medium"
        else:
            return "High"
    
    result["income_segment"] = result["median_income"].apply(assign_segment)
    
    # Convert to categorical for efficient grouping
    result["income_segment"] = pd.Categorical(
        result["income_segment"], 
        categories=["Low", "Medium", "High"],
        ordered=True
    )
    
    return result
