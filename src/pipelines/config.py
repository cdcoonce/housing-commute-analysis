from __future__ import annotations
import os
from pathlib import Path

# Navigate up from src/pipelines/config.py to project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_FINAL = PROJECT_ROOT / "data" / "final"
CACHE_DIR = PROJECT_ROOT / ".cache"
CACHE_DIR.mkdir(exist_ok=True, parents=True)

CENSUS_API_KEY = os.getenv("CENSUS_API_KEY", None)

# Metro Area Configurations
# Format: "metro_key": {
#   "name": Full metro name,
#   "cbsa_code": CBSA code from Census,
#   "counties": List of (state_fips, county_fips) tuples for all counties in metro,
#   "zip_prefixes": ZIP code prefixes for ZCTA queries,
#   "utm_zone": UTM zone EPSG code for accurate spatial calculations
# }
METRO_CONFIGS = {
    "phoenix": {
        "name": "Phoenix-Mesa-Chandler, AZ",
        "cbsa_code": "38060",
        "counties": [
            ("04", "013"),  # AZ - Maricopa
            ("04", "021"),  # AZ - Pinal
        ],
        "zip_prefixes": ["85"],
        "utm_zone": 32612  # UTM Zone 12N
    },
    "memphis": {
        "name": "Memphis, TN-MS-AR",
        "cbsa_code": "32820",
        "counties": [
            ("47", "157"),  # TN - Shelby
            ("47", "047"),  # TN - Fayette
            ("05", "035"),  # AR - Crittenden
            ("28", "033"),  # MS - DeSoto
        ],
        "zip_prefixes": ["38", "72", "386"],  # TN, AR, MS prefixes
        "utm_zone": 32616  # UTM Zone 16N
    },
    "los_angeles": {
        "name": "Los Angeles-Long Beach-Anaheim, CA",
        "cbsa_code": "31080",
        "counties": [
            ("06", "037"),  # CA - Los Angeles
        ],
        "zip_prefixes": ["90", "91"],  # Primary LA area prefixes
        "utm_zone": 32611  # UTM Zone 11N
    },
    "dallas": {
        "name": "Dallas-Fort Worth-Arlington, TX",
        "cbsa_code": "19100",
        "counties": [
            ("48", "113"),  # TX - Dallas
            ("48", "121"),  # TX - Denton
            ("48", "257"),  # TX - Collin
            ("48", "439"),  # TX - Tarrant
        ],
        "zip_prefixes": ["75", "76"],  # Dallas and Fort Worth areas
        "utm_zone": 32614  # UTM Zone 14N
    },
    "denver": {
        "name": "Denver-Aurora-Lakewood, CO",
        "cbsa_code": "19740",
        "counties": [
            ("08", "001"),  # CO - Adams
            ("08", "005"),  # CO - Arapahoe
            ("08", "013"),  # CO - Boulder
            ("08", "014"),  # CO - Broomfield
            ("08", "031"),  # CO - Denver
            ("08", "035"),  # CO - Douglas
            ("08", "039"),  # CO - Elbert
            ("08", "059"),  # CO - Jefferson
        ],
        "zip_prefixes": ["80", "81"],
        "utm_zone": 32613  # UTM Zone 13N
    },
    "atlanta": {
        "name": "Atlanta-Sandy Springs-Alpharetta, GA",
        "cbsa_code": "12060",
        "counties": [
            ("13", "121"),  # GA - Fulton
            ("13", "089"),  # GA - DeKalb
            ("13", "067"),  # GA - Cobb
            ("13", "063"),  # GA - Clayton
            ("13", "045"),  # GA - Cherokee
            ("13", "135"),  # GA - Gwinnett
            ("13", "151"),  # GA - Henry
            ("13", "057"),  # GA - Cherokee
        ],
        "zip_prefixes": ["30"],
        "utm_zone": 32616  # UTM Zone 16N
    },
    "chicago": {
        "name": "Chicago-Naperville-Elgin, IL-IN-WI",
        "cbsa_code": "16980",
        "counties": [
            ("17", "031"),  # IL - Cook
            ("17", "043"),  # IL - DuPage
            ("17", "089"),  # IL - Kane
            ("17", "097"),  # IL - Lake
            ("17", "111"),  # IL - McHenry
            ("17", "197"),  # IL - Will
        ],
        "zip_prefixes": ["60", "61", "62"],
        "utm_zone": 32616  # UTM Zone 16N
    },
    "seattle": {
        "name": "Seattle-Tacoma-Bellevue, WA",
        "cbsa_code": "42660",
        "counties": [
            ("53", "033"),  # WA - King
            ("53", "053"),  # WA - Pierce
            ("53", "061"),  # WA - Snohomish
        ],
        "zip_prefixes": ["98"],
        "utm_zone": 32610  # UTM Zone 10N
    },
    "miami": {
        "name": "Miami-Fort Lauderdale-Pompano Beach, FL",
        "cbsa_code": "33100",
        "counties": [
            ("12", "086"),  # FL - Miami-Dade
            ("12", "011"),  # FL - Broward
            ("12", "099"),  # FL - Palm Beach
        ],
        "zip_prefixes": ["33"],
        "utm_zone": 32617  # UTM Zone 17N
    }
}

# Select which metro to use (change this to switch metros)
SELECTED_METRO = os.getenv("METRO", "phoenix")  # Can be: phoenix, memphis, los_angeles, dallas

# Get the selected metro configuration
_metro_config = METRO_CONFIGS.get(SELECTED_METRO, METRO_CONFIGS["phoenix"])
CBSA_CODE = _metro_config["cbsa_code"]
COUNTIES = _metro_config["counties"]  # List of (state_fips, county_fips) tuples
ZIP_PREFIXES = _metro_config["zip_prefixes"]
UTM_ZONE = _metro_config["utm_zone"]
METRO_NAME = _metro_config["name"]

# Backward compatibility: extract unique states and primary state
STATES = sorted(set(state for state, _ in COUNTIES))
STATE_FIPS = STATES[0]  # Primary state (first alphabetically)
COUNTY_FIPS_LIST = [county for _, county in COUNTIES if _ == STATE_FIPS]  # Primary state counties only

# Zillow Research CSV URL for ZORI by ZIP (official data file; no public API)
# Update if Zillow changes paths.
ZORI_ZIP_CSV_URL = "https://files.zillowstatic.com/research/public_csvs/zori/Zip_zori_uc_sfrcondomfr_sm_sa_month.csv"

# Overpass transit feature filters (OpenStreetMap)
OSM_TRANSIT_NODE_FILTER = '["public_transport"~"platform|stop|station"]'
OSM_TRANSIT_FALLBACK = '["highway"="bus_stop"]'

# Output filename (includes metro name)
FINAL_ZCTA_OUT = DATA_FINAL / f"final_zcta_dataset_{SELECTED_METRO}.csv"