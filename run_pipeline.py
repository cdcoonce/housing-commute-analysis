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
import argparse
import logging
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    # Gracefully handle missing python-dotenv package
    def load_dotenv():
        pass

# Add project root to Python path to enable imports
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env file (must happen before local imports)
load_dotenv()

# Import after path setup and environment loading
from src.pipelines.build import build_final_dataset

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


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
    except (ValueError, KeyError) as e:
        # Handle data validation errors (missing columns, invalid metro codes)
        return False, f"Data validation error: {type(e).__name__}: {e}"
    except (FileNotFoundError, IOError, OSError) as e:
        # Handle file system errors (missing files, permission issues)
        return False, f"File system error: {type(e).__name__}: {e}"
    except Exception as e:
        # Catch unexpected errors with full type information
        logger.error(f"Unexpected error in {metro}: {type(e).__name__}: {e}", exc_info=True)
        return False, f"Unexpected error: {type(e).__name__}: {e}"
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
        help='Run pipeline for all metros sequentially (phoenix, memphis, los_angeles, dallas, denver, atlanta, chicago, seattle, miami)'
    )
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("DAT490 Housing Affordability Data Pipeline")
    logger.info("=" * 70)
    
    # Check if running all metros
    if args.all:
        all_metros = ["phoenix", "memphis", "los_angeles", "dallas", "denver", "atlanta", "chicago", "seattle", "miami"]
        logger.info(f"\nRunning pipeline for all metros: {', '.join(all_metros)}")
        logger.info(f"Census API Key: {'✓ Set' if os.getenv('CENSUS_API_KEY') else '✗ Not set (may hit rate limits)'}")
        logger.info("")
        
        results = []
        for metro in all_metros:
            logger.info("\n" + "=" * 70)
            logger.info(f"Processing: {metro}")
            logger.info("=" * 70)
            
            success, message = run_single_metro(metro)
            results.append((metro, success, message))
            
            if success:
                logger.info(f"✓ {metro} completed: {message}")
            else:
                logger.error(f"✗ {metro} failed: {message}")
        
        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("Pipeline Execution Summary")
        logger.info("=" * 70)
        
        success_count = sum(1 for _, success, _ in results if success)
        logger.info(f"Successful: {success_count} / {len(all_metros)}")
        
        failed_metros = [metro for metro, success, _ in results if not success]
        if failed_metros:
            logger.error(f"Failed metros: {', '.join(failed_metros)}")
            logger.error("\nFailed metro details:")
            for metro, success, message in results:
                if not success:
                    logger.error(f"  {metro}: {message}")
            return 1
        else:
            logger.info("All pipelines completed successfully!")
            logger.info("\nOutput files:")
            for metro, success, message in results:
                if success:
                    logger.info(f"  {message}")
            return 0
    
    # Single metro mode
    metro = os.getenv("METRO", "phoenix")
    logger.info("\nConfiguration:")
    logger.info(f"  Metro: {metro}")
    logger.info(f"  Census API Key: {'✓ Set' if os.getenv('CENSUS_API_KEY') else '✗ Not set (may hit rate limits)'}")
    logger.info("")
    
    try:
        # Run the pipeline
        output_path = build_final_dataset()
        
        logger.info("\n" + "=" * 70)
        logger.info("Pipeline completed successfully!")
        logger.info(f"Output: {output_path}")
        logger.info("=" * 70)
        
        return 0
        
    except Exception as e:
        logger.error("\n" + "=" * 70)
        logger.error("Pipeline failed with error:")
        logger.error(f"  {type(e).__name__}: {e}")
        logger.error("=" * 70)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
