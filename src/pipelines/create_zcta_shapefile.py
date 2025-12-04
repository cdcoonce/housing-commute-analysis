"""
Create ZCTA shapefiles for each metro area.

This script fetches ZCTA geometries for each configured metro area and saves them
as shapefiles for use in spatial analysis and choropleth mapping.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import METRO_CONFIGS, PROJECT_ROOT, CBSA_CODE, SELECTED_METRO, METRO_NAME
from tiger import get_cbsa_polygon, get_state_zctas
from spatial import filter_zctas_in_cbsa


def create_zcta_shapefile(metro_key: str = None) -> str:
    """
    Create a shapefile of ZCTAs for the specified metro area.
    
    Parameters
    ----------
    metro_key : str, optional
        Metro area key (e.g., 'phoenix', 'memphis'). If None, uses SELECTED_METRO from env.
    
    Returns
    -------
    str
        Path to the created shapefile directory
    """
    # Use selected metro if not specified
    if metro_key is None:
        metro_key = SELECTED_METRO
        config = METRO_CONFIGS[SELECTED_METRO]
        cbsa_code = CBSA_CODE
        metro_name = METRO_NAME
    else:
        config = METRO_CONFIGS[metro_key]
        cbsa_code = config["cbsa_code"]
        metro_name = config["name"]
    
    zip_prefixes = config['zip_prefixes']
    
    logger.info(f"\n{'='*80}")
    logger.info(f"Creating ZCTA Shapefile for {metro_name}")
    logger.info(f"{'='*80}\n")
    
    # Step 1: Fetch CBSA boundary
    logger.info(f"Fetching CBSA boundary (code: {cbsa_code})...")
    cbsa_boundary = get_cbsa_polygon(cbsa_code)
    logger.info(f"  ✓ CBSA boundary retrieved")
    
    # Step 2: Fetch ZCTAs by ZIP prefix
    print(f"\nFetching ZCTAs with prefixes: {zip_prefixes}...")
    zctas_all = get_state_zctas(zip_prefixes)
    print(f"  ✓ Retrieved {len(zctas_all)} total ZCTAs")
    
    # Step 3: Filter ZCTAs to those within CBSA boundary
    print(f"\nFiltering ZCTAs to {metro_name} metro area...")
    zctas_in_metro = filter_zctas_in_cbsa(zctas_all, cbsa_boundary)
    print(f"  ✓ Filtered to {len(zctas_in_metro)} ZCTAs within CBSA")
    
    # Step 4: Create output directory
    output_dir = PROJECT_ROOT / "data" / "shapefiles"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Step 5: Save as shapefile
    shapefile_path = output_dir / f"zcta_{metro_key}"
    zctas_in_metro.to_file(shapefile_path)
    
    logger.info(f"\n{'='*80}")
    logger.info(f"SUCCESS: ZCTA shapefile created")
    logger.info(f"{'='*80}")
    logger.info(f"  Metro: {metro_name}")
    logger.info(f"  ZCTAs: {len(zctas_in_metro)}")
    logger.info(f"  Output: {shapefile_path}")
    logger.info(f"  Files:")
    for file in shapefile_path.parent.glob(f"{shapefile_path.stem}.*"):
        logger.info(f"    - {file.name}")
    logger.info(f"\nColumns in shapefile:")
    print(f"  {', '.join(zctas_in_metro.columns.tolist())}")
    print(f"\nCRS: {zctas_in_metro.crs}")
    print()
    
    return str(shapefile_path)


def create_all_zcta_shapefiles():
    """Create ZCTA shapefiles for all configured metro areas."""
    print(f"\n{'='*80}")
    print(f"Creating ZCTA Shapefiles for All Metro Areas")
    print(f"{'='*80}\n")
    
    results = {}
    for metro_key in METRO_CONFIGS.keys():
        try:
            shapefile_path = create_zcta_shapefile(metro_key)
            results[metro_key] = shapefile_path
            print()
        except Exception as e:
            print(f"ERROR: Failed to create shapefile for {metro_key}: {e}\n")
            results[metro_key] = None
    
    print(f"\n{'='*80}")
    print(f"Summary")
    print(f"{'='*80}")
    for metro_key, path in results.items():
        status = "✓" if path else "✗"
        print(f"  {status} {metro_key}: {path if path else 'Failed'}")
    print()
    
    return results


if __name__ == "__main__":
    import sys
    
    # Check if user wants to create all shapefiles
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        create_all_zcta_shapefiles()
    else:
        # Create shapefile for selected metro (from METRO env var)
        create_zcta_shapefile()
