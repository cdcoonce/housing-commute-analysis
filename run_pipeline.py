#!/usr/bin/env python3
"""Main entry point for running the housing affordability data pipeline.

This script orchestrates the complete data pipeline that:
1. Fetches geographic boundaries (CBSAs, ZCTAs, census tracts)
2. Retrieves ACS demographic and commute data
3. Fetches Zillow rent data (ZORI)
4. Computes OpenStreetMap transit density
5. Aggregates and merges all data into final ZCTA-level dataset

Usage:
    # Run for default metro (Phoenix)
    python run_pipeline.py
    
    # Run for specific metro
    METRO=dallas python run_pipeline.py
    
    # With Census API key
    CENSUS_API_KEY=your_key_here python run_pipeline.py

Environment Variables:
    METRO: Metro area to process (phoenix, memphis, los_angeles, dallas)
    CENSUS_API_KEY: Census API key (optional but recommended for reliability)
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Add project root to Python path to enable imports
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env file
load_dotenv()

from src.pipelines.build import build_final_dataset


def main():
    """Execute the data pipeline."""
    print("=" * 70)
    print("DAT490 Housing Affordability Data Pipeline")
    print("=" * 70)
    
    # Display configuration
    metro = os.getenv("METRO", "phoenix")
    print(f"\nConfiguration:")
    print(f"  Metro: {metro}")
    print(f"  Census API Key: {'✓ Set' if os.getenv('CENSUS_API_KEY') else '✗ Not set (may hit rate limits)'}")
    print()
    
    try:
        # Run the pipeline
        output_path = build_final_dataset()
        
        print("\n" + "=" * 70)
        print("Pipeline completed successfully!")
        print(f"Output: {output_path}")
        print("=" * 70)
        
        return 0
        
    except Exception as e:
        print("\n" + "=" * 70)
        print("Pipeline failed with error:")
        print(f"  {type(e).__name__}: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
