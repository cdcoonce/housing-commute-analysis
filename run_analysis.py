#!/usr/bin/env python3
"""
DAT490 Capstone Analysis: The Housing-Commute Trade-Off
Main orchestration script for ZCTA-level analysis across four metros.

This script provides the CLI interface and coordinates the analysis workflow
by calling specialized functions from modular analysis modules.

Author: DAT490 Team
Date: November 2025
"""

import argparse
import logging
from pathlib import Path

import matplotlib as mpl

# Import from src.models analysis modules
from src.models.data_loader import METRO_FILES, METRO_NAMES, load_and_validate_data
from src.models.rq1_housing_commute_tradeoff import run_rq1

# Optional imports for additional research questions (if implemented)
try:
    from src.models.rq2_equity_analysis import run_rq2
    HAS_RQ2 = True
except ImportError:
    HAS_RQ2 = False

try:
    from src.models.rq3_aci_analysis import run_rq3
    HAS_RQ3 = True
except ImportError:
    HAS_RQ3 = False

# Set matplotlib style for publication-quality plots
mpl.style.use('seaborn-v0_8-darkgrid')

# Logging configuration - INFO level for progress tracking
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description='DAT490 Housing-Commute Trade-Off Analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--metro',
        type=str,
        required=True,
        choices=['PHX', 'LA', 'DFW', 'MEM'],
        help='Metro area code (PHX, LA, DFW, MEM)'
    )
    
    parser.add_argument(
        '--raw-dir',
        type=str,
        default='data/final',
        help='Directory containing raw CSV files'
    )
    
    parser.add_argument(
        '--out-dir',
        type=str,
        default='data/processed',
        help='Output directory for processed data and results'
    )
    
    parser.add_argument(
        '--fig-dir',
        type=str,
        default='figures',
        help='Output directory for figures'
    )
    
    parser.add_argument(
        '--zcta-shp',
        type=str,
        default=None,
        help='Path to ZCTA shapefile (optional, for choropleth maps)'
    )
    
    args = parser.parse_args()
    
    # Setup paths
    raw_dir = Path(args.raw_dir)
    out_dir = Path(args.out_dir) / args.metro
    fig_dir = Path(args.fig_dir) / args.metro
    
    # Create output directories
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("=" * 70)
    logger.info("DAT490 CAPSTONE ANALYSIS: THE HOUSING-COMMUTE TRADE-OFF")
    logger.info("=" * 70)
    logger.info(f"Metro: {METRO_NAMES[args.metro]}")
    logger.info(f"Output directory: {out_dir}")
    logger.info(f"Figure directory: {fig_dir}")
    logger.info("=" * 70)
    
    # Load data
    csv_file = raw_dir / METRO_FILES[args.metro]
    
    if not csv_file.exists():
        logger.error(f"CSV file not found: {csv_file}")
        logger.error(f"Please ensure {METRO_FILES[args.metro]} exists in {raw_dir}")
        return
    
    df = load_and_validate_data(csv_file, args.metro)
    
    # Save cleaned data
    cleaned_path = out_dir / f"cleaned_data_{args.metro.lower()}.csv"
    df.write_csv(cleaned_path)
    logger.info(f"Saved cleaned data to {cleaned_path}")
    
    # Run analyses
    try:
        # RQ1: Housing-Commute Trade-Off (always run)
        logger.info("\n" + "=" * 70)
        logger.info("Running RQ1: Housing-Commute Trade-Off Analysis")
        logger.info("=" * 70)
        run_rq1(df, out_dir, fig_dir, args.metro)
        
        # RQ2: Equity Analysis (if implemented)
        if HAS_RQ2:
            logger.info("\n" + "=" * 70)
            logger.info("Running RQ2: Equity Analysis")
            logger.info("=" * 70)
            run_rq2(df, out_dir, fig_dir, args.metro)
        else:
            logger.info("\nRQ2: Equity Analysis - SKIPPED (module not implemented)")
        
        # RQ3: ACI Analysis (if implemented)
        if HAS_RQ3:
            # Auto-detect shapefile if not provided
            if args.zcta_shp:
                zcta_shp = Path(args.zcta_shp)
            else:
                # Try to auto-detect based on metro code
                metro_shp_map = {
                    'PHX': 'phoenix',
                    'LA': 'los_angeles', 
                    'DFW': 'dallas',
                    'MEM': 'memphis'
                }
                
                shp_name = metro_shp_map.get(args.metro)
                if shp_name:
                    # Try multiple possible locations
                    possible_paths = [
                        Path('data') / 'shapefiles' / f'zcta_{shp_name}' / f'zcta_{shp_name}.shp',
                        raw_dir.parent / 'shapefiles' / f'zcta_{shp_name}' / f'zcta_{shp_name}.shp',
                    ]
                    
                    zcta_shp = None
                    for path in possible_paths:
                        if path.exists():
                            zcta_shp = path
                            logger.info(f"Auto-detected shapefile: {path}")
                            break
                    
                    if zcta_shp is None:
                        logger.warning(f"Shapefile not found. Tried: {[str(p) for p in possible_paths]}")
                else:
                    zcta_shp = None
            
            logger.info("\n" + "=" * 70)
            logger.info("Running RQ3: ACI Analysis")
            logger.info("=" * 70)
            run_rq3(df, out_dir, fig_dir, args.metro, zcta_shp)
        else:
            logger.info("\nRQ3: ACI Analysis - SKIPPED (module not implemented)")
        
        logger.info("\n" + "=" * 70)
        logger.info("ANALYSIS COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Metro: {METRO_NAMES[args.metro]}")
        logger.info(f"Results saved to: {out_dir}")
        logger.info(f"Figures saved to: {fig_dir}")
        logger.info(f"Cleaned data: {cleaned_path}")
        
        # List generated files
        result_files = sorted(out_dir.glob('*.csv')) + sorted(out_dir.glob('*.md'))
        if result_files:
            logger.info(f"\nGenerated {len(result_files)} result file(s):")
            for f in result_files[:10]:  # Show first 10 files
                logger.info(f"  - {f.name}")
            if len(result_files) > 10:
                logger.info(f"  ... and {len(result_files) - 10} more")
        
        figure_files = sorted(fig_dir.glob('*.png')) + sorted(fig_dir.glob('*.pdf'))
        if figure_files:
            logger.info(f"\nGenerated {len(figure_files)} figure(s):")
            for f in figure_files[:10]:  # Show first 10 figures
                logger.info(f"  - {f.name}")
            if len(figure_files) > 10:
                logger.info(f"  ... and {len(figure_files) - 10} more")
        
        logger.info("=" * 70)
        
    except (ValueError, KeyError) as e:
        # Handle data validation or missing column errors with specific context
        logger.error(
            f"Data validation error in {args.metro}: {e}. "
            "Check that all required columns exist and data types are correct.",
            exc_info=True
        )
        raise
    except FileNotFoundError as e:
        # Handle missing file errors (more specific than IOError, must come first)
        logger.error(
            f"Required file not found: {e}. "
            f"Expected CSV: {csv_file}. Check data/raw directory.",
            exc_info=False  # Don't need full stack trace for missing file
        )
        raise
    except (IOError, OSError) as e:
        # Handle other file I/O errors (permissions, disk full, etc.)
        logger.error(
            f"File operation error in {args.metro}: {e}. "
            f"Verify file paths and permissions: raw_dir={raw_dir}, out_dir={out_dir}",
            exc_info=True
        )
        raise
    except Exception as e:
        # Catch any unexpected errors with full diagnostic context
        logger.error(
            f"Unexpected error during analysis for {args.metro}: {type(e).__name__}: {e}. "
            "This may indicate a bug in the analysis code.",
            exc_info=True
        )
        raise


if __name__ == "__main__":
    main()
