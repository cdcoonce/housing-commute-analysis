"""Export simplified per-metro ZCTA GeoJSON for the explorer's map layer.

Source: the Census cartographic-boundary ZCTA file (cb_2020_us_zcta520_500k),
the same source documented in ``data/raw/shapefiles/README.md`` — downloaded
once into ``.cache/`` and reused. Each metro's file is filtered to the ZCTAs
of its committed 35-column dataset, simplified for the web, and joined with
the map's display properties:

- ``covered``: whether the ZCTA appears in the committed ZORI panel
- ``commute``: ACS 2015-2019 commute proxy (minutes)
- ``dist``: distance to CBD (km, from the committed cross-section)
- ``logacc``: log 2019 LODES gravity job accessibility

Usage:
    uv run python scripts/export_explorer_geojson.py [METRO ...]
"""

from __future__ import annotations

import io
import json
import logging
import math
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.data_loader import METRO_FILES  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

METROS = ["PHX", "LA", "DFW", "MEM", "DEN", "ATL", "CHI", "SEA", "MIA"]
FINAL_DIR = ROOT / "data" / "final"
OUT_DIR = ROOT / "explorer" / "data"
CACHE = ROOT / ".cache" / "cb_2020_us_zcta520_500k.zip"
CB_URL = (
    "https://www2.census.gov/geo/tiger/GENZ2020/shp/"
    "cb_2020_us_zcta520_500k.zip"
)
SIMPLIFY_TOLERANCE = 0.003  # degrees, on top of the 1:500k base
COORD_DECIMALS = 4


def national_zctas() -> gpd.GeoDataFrame:
    if not CACHE.exists():
        logger.info("downloading %s ...", CB_URL)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(CB_URL, timeout=300)
        resp.raise_for_status()
        CACHE.write_bytes(resp.content)
        logger.info("cached %.1f MB", len(resp.content) / 1e6)
    with zipfile.ZipFile(io.BytesIO(CACHE.read_bytes())) as zf:
        shp = [n for n in zf.namelist() if n.endswith(".shp")][0]
    gdf = gpd.read_file(f"zip://{CACHE}!{shp}")
    key = "ZCTA5CE20" if "ZCTA5CE20" in gdf.columns else "ZCTA5CE"
    return gdf.rename(columns={key: "ZCTA5CE"})[["ZCTA5CE", "geometry"]]


def metro_frame(metro: str) -> pd.DataFrame:
    key = METRO_FILES[metro].replace("final_zcta_dataset_", "").replace(".csv", "")
    cross = pd.read_csv(
        FINAL_DIR / METRO_FILES[metro], dtype={"ZCTA5CE": str}
    )
    cross["ZCTA5CE"] = cross["ZCTA5CE"].str.zfill(5)
    acs = pd.read_csv(
        FINAL_DIR / f"acs_commute_2019_{key}.csv", dtype={"ZCTA5CE": str}
    )
    lodes = pd.read_csv(
        FINAL_DIR / f"lodes_panel_{key}.csv", dtype={"ZCTA5CE": str}
    )
    lodes19 = lodes[lodes["year"] == 2019][["ZCTA5CE", "job_accessibility"]]
    zori = pd.read_csv(
        FINAL_DIR / f"zori_panel_{key}.csv", dtype={"ZCTA5CE": str}
    )
    covered = set(zori["ZCTA5CE"])

    df = cross[["ZCTA5CE", "distance_to_cbd_km"]].merge(
        acs[["ZCTA5CE", "commute_min_proxy_2019"]], on="ZCTA5CE", how="left"
    ).merge(lodes19, on="ZCTA5CE", how="left")
    df["covered"] = df["ZCTA5CE"].isin(covered)
    df["logacc"] = df["job_accessibility"].map(
        lambda v: math.log(v) if pd.notna(v) and v > 0 else None
    )
    return df


def export_metro(metro: str, national: gpd.GeoDataFrame) -> None:
    df = metro_frame(metro)
    gdf = national.merge(df, on="ZCTA5CE", how="inner")
    missing = set(df["ZCTA5CE"]) - set(gdf["ZCTA5CE"])
    if missing:
        logger.warning("%s: %d ZCTAs missing geometry: %s",
                       metro, len(missing), sorted(missing)[:5])
    gdf["geometry"] = gdf.geometry.simplify(SIMPLIFY_TOLERANCE)

    features = []
    for row in gdf.itertuples():
        geom = gpd.GeoSeries([row.geometry]).__geo_interface__["features"][0][
            "geometry"
        ]
        geom = _round_geom(geom)
        features.append({
            "type": "Feature",
            "properties": {
                "z": row.ZCTA5CE,
                "covered": bool(row.covered),
                "commute": _r(row.commute_min_proxy_2019, 1),
                "dist": _r(row.distance_to_cbd_km, 1),
                "logacc": _r(row.logacc, 2),
            },
            "geometry": geom,
        })
    out = OUT_DIR / f"geo_{metro.lower()}.json"
    out.write_text(json.dumps(
        {"type": "FeatureCollection", "features": features},
        separators=(",", ":"),
    ))
    logger.info("%s: %d ZCTAs -> %s (%.0f KB)",
                metro, len(features), out.name, out.stat().st_size / 1024)


def _r(v, d):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), d)


def _round_geom(geom: dict) -> dict:
    def rec(c):
        if isinstance(c, (list, tuple)):
            if c and isinstance(c[0], (int, float)):
                return [round(c[0], COORD_DECIMALS), round(c[1], COORD_DECIMALS)]
            return [rec(x) for x in c]
        return c
    return {"type": geom["type"], "coordinates": rec(geom["coordinates"])}


def main() -> int:
    metros = [m.upper() for m in sys.argv[1:]] or METROS
    national = national_zctas()
    logger.info("national ZCTA frame: %d rows", len(national))
    for metro in metros:
        export_metro(metro, national)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
