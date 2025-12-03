"""
Configuration management for DAT490 project.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
MODELS_DIR = DATA_DIR / "models"

# Ensure directories exist
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# API Keys (if needed)
ZILLOW_API_KEY = os.getenv("ZILLOW_API_KEY", "")
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY", "")

# Metro configurations
METRO_CONFIGS = {
    "phoenix": {
        "name": "Phoenix-Mesa-Chandler, AZ",
        "cbsa_code": "38060",
        "state_fips": "04",
        "county_fips_list": ["013", "021"],
        "zip_prefixes": ["85"],
        "utm_zone": 32612
    },
    "memphis": {
        "name": "Memphis, TN-MS-AR",
        "cbsa_code": "32820",
        "state_fips": "47",
        "county_fips_list": ["157", "047", "033"],
        "zip_prefixes": ["38", "72"],
        "utm_zone": 32616
    },
    "los_angeles": {
        "name": "Los Angeles-Long Beach-Anaheim, CA",
        "cbsa_code": "31080",
        "state_fips": "06",
        "county_fips_list": ["037"],
        "zip_prefixes": ["90", "91"],
        "utm_zone": 32611
    },
    "dallas": {
        "name": "Dallas-Fort Worth-Arlington, TX",
        "cbsa_code": "19100",
        "state_fips": "48",
        "county_fips_list": ["113", "085", "121", "257", "439"],
        "zip_prefixes": ["75", "76"],
        "utm_zone": 32614
    }
}
