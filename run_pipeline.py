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

# Offline Prefect defaults MUST be set before build (and thus prefect) is
# imported so a fresh clone runs the flow with zero Prefect setup.
os.environ.setdefault("PREFECT_HOME", str(PROJECT_ROOT / ".prefect"))
os.environ.setdefault("PREFECT_SERVER_ALLOW_EPHEMERAL_MODE", "true")
os.environ.setdefault("PREFECT_RESULTS_LOCAL_STORAGE_PATH", str(PROJECT_ROOT / ".prefect_cache"))

# Import after path setup and environment loading
from src.pipelines.build import build_final_dataset  # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
# Prefect's logging config resets the root logger to WARNING when a flow runs;
# pin this module's logger to INFO so --verify/--generate-manifests output
# stays visible (mirrors run_analysis.py).
logger.setLevel(logging.INFO)


def run_single_metro(metro: str) -> tuple[bool, str]:
    """Run the pipeline for a single metro area.

    Parameters
    ----------
    metro : str
        Metro area key (e.g., 'phoenix', 'dallas', 'atlanta').

    Returns
    -------
    tuple[bool, str]
        (success, output_path or error_message)
    """
    try:
        output_path = build_final_dataset(metro_key=metro)
        return True, str(output_path)
    except (ValueError, KeyError) as e:
        return False, f"Data validation error: {type(e).__name__}: {e}"
    except (FileNotFoundError, IOError, OSError) as e:
        return False, f"File system error: {type(e).__name__}: {e}"
    except Exception as e:
        logger.error(f"Unexpected error in {metro}: {type(e).__name__}: {e}", exc_info=True)
        return False, f"Unexpected error: {type(e).__name__}: {e}"


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
    parser.add_argument("--generate-manifests", action="store_true",
                        help="Offline: (re)write provenance manifests for existing final CSVs")
    parser.add_argument("--verify", action="store_true",
                        help="Offline: verify final CSVs against committed manifests (no network)")
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("DAT490 Housing Affordability Data Pipeline")
    logger.info("=" * 70)

    if args.generate_manifests:
        from datetime import datetime, timezone

        import polars as pl

        from src.pipelines.config import DATA_FINAL, METRO_CONFIGS
        from src.pipelines.manifest import build_manifest, get_git_commit, write_manifest

        commit = get_git_commit()
        ts = datetime.now(timezone.utc).isoformat()
        count = 0
        for metro_key in METRO_CONFIGS:
            csv = DATA_FINAL / f"final_zcta_dataset_{metro_key}.csv"
            if not csv.exists():
                continue
            df = pl.read_csv(csv)
            zori_period = None
            if "period" in df.columns and df["period"].drop_nulls().len() > 0:
                zori_period = str(df["period"].drop_nulls().max())
            write_manifest(
                build_manifest(metro_key, csv, git_commit=commit, timestamp_utc=ts,
                               zori_period=zori_period, steps=[]),
                DATA_FINAL / f"{metro_key}.manifest.json",
            )
            count += 1
            logger.info("wrote manifest for %s", metro_key)
        logger.info("Generated %d manifests", count)
        return 0

    if args.verify:
        from src.pipelines.config import DATA_FINAL
        from src.pipelines.manifest import verify_manifest

        manifests = sorted(DATA_FINAL.glob("*.manifest.json"))
        if not manifests:
            logger.warning("No manifests found in %s — run --generate-manifests first.", DATA_FINAL)
            return 0
        any_drift = False
        for mpath in manifests:
            metro_key = mpath.stem.replace(".manifest", "")
            csv = DATA_FINAL / f"final_zcta_dataset_{metro_key}.csv"
            drift = verify_manifest(csv, mpath)
            if drift:
                any_drift = True
                logger.error("DRIFT %s: %s", metro_key, "; ".join(drift))
            else:
                logger.info("OK %s", metro_key)
        return 1 if any_drift else 0

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
        output_path = build_final_dataset(metro_key=metro)
        
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
