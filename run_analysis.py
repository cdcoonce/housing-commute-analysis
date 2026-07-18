#!/usr/bin/env python3
"""
DAT490 Capstone Analysis: The Housing-Commute Trade-Off
Main orchestration script for ZCTA-level analysis across nine metros.

This script provides the CLI interface and coordinates the analysis workflow
by calling specialized functions from modular analysis modules. The per-metro
work runs as a Prefect flow, with a ``--all`` batch mode that dispatches the
flow across every metro.

Author: DAT490 Team
Date: November 2025
"""

import argparse
import logging
import os
from pathlib import Path

# Offline Prefect defaults MUST be set before prefect is imported so a fresh
# clone runs with no server/setup (ephemeral mode, local result storage).
PROJECT_ROOT = Path(__file__).resolve().parent
os.environ.setdefault("PREFECT_HOME", str(PROJECT_ROOT / ".prefect"))
os.environ.setdefault("PREFECT_SERVER_ALLOW_EPHEMERAL_MODE", "true")
os.environ.setdefault("PREFECT_RESULTS_LOCAL_STORAGE_PATH", str(PROJECT_ROOT / ".prefect_cache"))
# Enforce local-only runs: drop any inherited PREFECT_API_URL so a developer with
# Prefect Cloud exported can't accidentally make a real run contact a server.
os.environ.pop("PREFECT_API_URL", None)

from prefect import flow  # noqa: E402

# Import from src.models analysis modules
from src.models.data_loader import METRO_FILES, METRO_NAMES, load_and_validate_data  # noqa: E402
from src.models.rq1_housing_commute_tradeoff import run_rq1  # noqa: E402

# Optional imports for additional research questions (if implemented)
try:
    from src.models.rq2_equity_analysis import run_rq2  # noqa: E402
    HAS_RQ2 = True
except ImportError:
    run_rq2 = None  # Explicitly set to None to prevent unbound errors
    HAS_RQ2 = False

try:
    from src.models.rq3_aci_analysis import run_rq3  # noqa: E402
    HAS_RQ3 = True
except ImportError:
    run_rq3 = None  # Explicitly set to None to prevent unbound errors
    HAS_RQ3 = False

try:
    from src.models.rq4_rent_dynamics import run_rq4  # noqa: E402
    HAS_RQ4 = True
except ImportError:
    run_rq4 = None  # Explicitly set to None to prevent unbound errors
    HAS_RQ4 = False

# Logging configuration - INFO level for progress tracking
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# Prefect's logging config resets the root logger to WARNING when a flow runs;
# pin this module's logger to INFO so progress banners and the per-metro summary
# stay visible (routed through Prefect's console handler).
logger.setLevel(logging.INFO)


def _auto_shapefile(metro: str, raw_dir: Path, zcta_shp: str | None) -> Path | None:
    """Resolve the ZCTA shapefile for a metro.

    If ``zcta_shp`` is given, use it directly; otherwise auto-detect based on the
    metro code by probing known shapefile locations. Returns ``None`` when no
    shapefile can be resolved.
    """
    if zcta_shp:
        return Path(zcta_shp)

    # Try to auto-detect based on metro code
    metro_shp_map = {
        'PHX': 'phoenix',
        'LA': 'los_angeles',
        'DFW': 'dallas',
        'MEM': 'memphis',
        'DEN': 'denver',
        'ATL': 'atlanta',
        'CHI': 'chicago',
        'SEA': 'seattle',
        'MIA': 'miami',
    }

    shp_name = metro_shp_map.get(metro)
    if not shp_name:
        return None

    # Try multiple possible locations
    possible_paths = [
        Path('data') / 'shapefiles' / f'zcta_{shp_name}' / f'zcta_{shp_name}.shp',
        raw_dir.parent / 'shapefiles' / f'zcta_{shp_name}' / f'zcta_{shp_name}.shp',
    ]

    for path in possible_paths:
        if path.exists():
            logger.info(f"Auto-detected shapefile: {path}")
            return path

    logger.warning(f"Shapefile not found. Tried: {[str(p) for p in possible_paths]}")
    return None


@flow(name="analyze-metro")
def analyze_metro_flow(metro: str, raw_dir: Path, out_base: Path, fig_base: Path,
                       zcta_shp: str | None) -> tuple[bool, str]:
    """Run RQ1/RQ2/RQ3/RQ4 for a single metro. Returns ``(success, message)``.

    RQ4 additionally needs the committed panel products in ``raw_dir``
    (zori/lodes/acs-2019); when any is absent it is skipped with a log line
    and the metro still succeeds (RQ1-RQ3 unaffected).

    On failure the metro is logged and ``(False, message)`` is returned rather
    than raising, so a batch run can continue past one metro's failure. The
    process still exits non-zero via ``main`` when any metro fails.
    """
    out_dir = out_base / metro
    fig_dir = fig_base / metro

    # Create output directories
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 70)
    logger.info("DAT490 CAPSTONE ANALYSIS: THE HOUSING-COMMUTE TRADE-OFF")
    logger.info("=" * 70)
    logger.info(f"Metro: {METRO_NAMES[metro]}")
    logger.info(f"Output directory: {out_dir}")
    logger.info(f"Figure directory: {fig_dir}")
    logger.info("=" * 70)

    # Load data
    csv_file = raw_dir / METRO_FILES[metro]

    if not csv_file.exists():
        logger.error(f"CSV file not found: {csv_file}")
        logger.error(f"Please ensure {METRO_FILES[metro]} exists in {raw_dir}")
        return False, f"CSV not found: {csv_file}"

    try:
        df = load_and_validate_data(csv_file, metro)

        # Save cleaned data
        cleaned_path = out_dir / f"cleaned_data_{metro.lower()}.csv"
        df.write_csv(cleaned_path)
        logger.info(f"Saved cleaned data to {cleaned_path}")

        # RQ1: Housing-Commute Trade-Off (always run)
        logger.info("\n" + "=" * 70)
        logger.info("Running RQ1: Housing-Commute Trade-Off Analysis")
        logger.info("=" * 70)
        run_rq1(df, out_dir, fig_dir, metro)

        # RQ2: Equity Analysis (if implemented)
        if HAS_RQ2 and run_rq2 is not None:
            logger.info("\n" + "=" * 70)
            logger.info("Running RQ2: Equity Analysis")
            logger.info("=" * 70)
            run_rq2(df, out_dir, fig_dir, metro)
        else:
            logger.info("\nRQ2: Equity Analysis - SKIPPED (module not implemented)")

        # RQ3: ACI Analysis (if implemented)
        if HAS_RQ3 and run_rq3 is not None:
            logger.info("\n" + "=" * 70)
            logger.info("Running RQ3: ACI Analysis")
            logger.info("=" * 70)
            run_rq3(df, out_dir, fig_dir, metro, _auto_shapefile(metro, raw_dir, zcta_shp))
        else:
            logger.info("\nRQ3: ACI Analysis - SKIPPED (module not implemented)")

        # RQ4: ZORI Rent Dynamics (needs the committed panel products; an
        # old checkout or partial rebuild without them still runs RQ1-RQ3)
        if HAS_RQ4 and run_rq4 is not None:
            try:
                logger.info("\n" + "=" * 70)
                logger.info("Running RQ4: ZORI Rent Dynamics Analysis")
                logger.info("=" * 70)
                run_rq4(df, out_dir, fig_dir, metro, raw_dir)
            except FileNotFoundError as exc:
                logger.info(
                    "RQ4: ZORI Rent Dynamics - SKIPPED (panel files absent "
                    "in %s: %s)", raw_dir, exc
                )
        else:
            logger.info("\nRQ4: ZORI Rent Dynamics - SKIPPED (module not implemented)")

        logger.info("\n" + "=" * 70)
        logger.info("ANALYSIS COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Metro: {METRO_NAMES[metro]}")
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
        return True, str(out_dir)

    except Exception as e:  # noqa: BLE001 — surface per-metro failure without aborting the batch
        logger.error("Analysis failed for %s: %s", metro, e, exc_info=True)
        return False, f"{type(e).__name__}: {e}"


@flow(name="analyze-all-metros")
def analyze_all_metros(raw_dir: Path, out_base: Path, fig_base: Path,
                       zcta_shp: str | None) -> list[tuple[str, bool, str]]:
    """Run the analysis flow for every metro. Returns ``[(metro, success, message)]``."""
    results: list[tuple[str, bool, str]] = []
    for metro in METRO_FILES:
        ok, msg = analyze_metro_flow(metro, raw_dir, out_base, fig_base, zcta_shp)
        results.append((metro, ok, msg))
    return results


def main() -> None:
    """Parse CLI arguments and dispatch the analysis flow(s)."""
    parser = argparse.ArgumentParser(
        description='DAT490 Housing-Commute Trade-Off Analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--metro',
        type=str,
        required=False,
        choices=['PHX', 'LA', 'DFW', 'MEM', 'DEN', 'ATL', 'CHI', 'SEA', 'MIA'],
        help='Metro area code (PHX, LA, DFW, MEM, DEN, ATL, CHI, SEA, MIA)'
    )

    parser.add_argument(
        '--all',
        action='store_true',
        help='Run analysis for all metros'
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

    # Require exactly one of --metro / --all
    if bool(args.metro) == bool(args.all):
        parser.error("provide exactly one of --metro CODE or --all")

    raw_dir = Path(args.raw_dir)
    out_base = Path(args.out_dir)
    fig_base = Path(args.fig_dir)

    if args.all:
        results = analyze_all_metros(raw_dir, out_base, fig_base, args.zcta_shp)
    else:
        ok, msg = analyze_metro_flow(args.metro, raw_dir, out_base, fig_base, args.zcta_shp)
        results = [(args.metro, ok, msg)]

    failed = [m for m, ok, _ in results if not ok]
    for m, ok, msg in results:
        logger.info("%s %s: %s", "✓" if ok else "✗", m, msg)
    if failed:
        logger.error("Failed: %s", ", ".join(failed))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
