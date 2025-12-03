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
    
    # Run for all metros sequentially
    python run_pipeline.py --all
    
    # With Census API key
    CENSUS_API_KEY=your_key_here python run_pipeline.py

Environment Variables:
    METRO: Metro area to process (phoenix, memphis, los_angeles, dallas)
    CENSUS_API_KEY: Census API key (optional but recommended for reliability)
"""
import sys
import os
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Add project root to Python path to enable imports
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env file
load_dotenv()

from src.pipelines.build import build_final_dataset


def run_single_metro(metro: str) -> tuple[bool, str]:
    """
    Run the pipeline for a single metro area.
    
    Parameters
    ----------
    metro : str
        Metro area code (phoenix, memphis, los_angeles, dallas)
    
    Returns
    -------
    tuple[bool, str]
        (success, output_path or error_message)
    """
    # Temporarily set METRO environment variable
    original_metro = os.getenv("METRO")
    os.environ["METRO"] = metro
    
    try:
        output_path = build_final_dataset()
        return True, str(output_path)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    finally:
        # Restore original METRO value
        if original_metro is not None:
            os.environ["METRO"] = original_metro
        elif "METRO" in os.environ:
            del os.environ["METRO"]


def main():
    """Execute the data pipeline."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Run the housing affordability data pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Run pipeline for all metros sequentially (phoenix, memphis, los_angeles, dallas)'
    )
    args = parser.parse_args()
    
    print("=" * 70)
    print("DAT490 Housing Affordability Data Pipeline")
    print("=" * 70)
    
    # Check if running all metros
    if args.all:
        all_metros = ["phoenix", "memphis", "los_angeles", "dallas"]
        print(f"\nRunning pipeline for all metros: {', '.join(all_metros)}")
        print(f"Census API Key: {'✓ Set' if os.getenv('CENSUS_API_KEY') else '✗ Not set (may hit rate limits)'}")
        print()
        
        results = []
        for metro in all_metros:
            print("\n" + "=" * 70)
            print(f"Processing: {metro}")
            print("=" * 70)
            
            success, message = run_single_metro(metro)
            results.append((metro, success, message))
            
            if success:
                print(f"✓ {metro} completed: {message}")
            else:
                print(f"✗ {metro} failed: {message}")
        
        # Summary
        print("\n" + "=" * 70)
        print("Pipeline Execution Summary")
        print("=" * 70)
        
        success_count = sum(1 for _, success, _ in results if success)
        print(f"Successful: {success_count} / {len(all_metros)}")
        
        failed_metros = [metro for metro, success, _ in results if not success]
        if failed_metros:
            print(f"Failed metros: {', '.join(failed_metros)}")
            print("\nFailed metro details:")
            for metro, success, message in results:
                if not success:
                    print(f"  {metro}: {message}")
            return 1
        else:
            print("All pipelines completed successfully!")
            print("\nOutput files:")
            for metro, success, message in results:
                if success:
                    print(f"  {message}")
            return 0
    
    # Single metro mode
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
