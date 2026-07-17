"""Provenance manifest for final datasets: sha256 + schema + source vintages."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import polars as pl

from src.pipelines.acs import DEFAULT_ACS_YEAR  # ACS commute vintage (2021)
from src.pipelines.config import METRO_CONFIGS, ZORI_ZIP_CSV_URL
from src.pipelines.lodes import LODES_YEAR

_DEMOGRAPHICS_YEAR = 2023  # fetch_demographics_for_county default vintage
_SOURCE_URLS = {
    "acs": f"https://api.census.gov/data/{DEFAULT_ACS_YEAR}/acs/acs5",
    "acs_demographics": f"https://api.census.gov/data/{_DEMOGRAPHICS_YEAR}/acs/acs5",
    "zori": ZORI_ZIP_CSV_URL,
    "tiger": "https://tigerweb.geo.census.gov/arcgis/rest/services (CBSA/ZCTA/tract)",
    "osm": "https://overpass-api.de (via OSMnx)",
    "lodes": f"https://lehd.ces.census.gov/data/lodes/LODES8 (WAC S000_JT00 {LODES_YEAR} + xwalk)",
}


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get_git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _metro_config_snapshot(metro_key: str) -> dict[str, Any] | None:
    """JSON-serializable snapshot of the producing metro's config essentials.

    Records the county list (and friends) in the manifest so a silent config
    change is visible as provenance drift. Unknown metros (e.g. the "test"
    metro used in tests) yield None rather than raising.
    """
    config = METRO_CONFIGS.get(metro_key)
    if config is None:
        return None
    return {
        "cbsa_code": config["cbsa_code"],
        "counties": [list(county) for county in config["counties"]],
        "zip_prefixes": list(config["zip_prefixes"]),
        "utm_zone": config["utm_zone"],
        "cbd_points": [list(point) for point in config["cbd_points"]],
    }


def build_manifest(
    metro_key: str,
    csv_path: Path,
    *,
    git_commit: str,
    timestamp_utc: str,
    zori_period: str | None,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    df = pl.read_csv(csv_path)
    return {
        "metro_key": metro_key,
        "metro_config": _metro_config_snapshot(metro_key),
        "git_commit": git_commit,
        "run_timestamp_utc": timestamp_utc,
        "acs_commute_year": DEFAULT_ACS_YEAR,
        "acs_demographics_year": _DEMOGRAPHICS_YEAR,
        "lodes_year": LODES_YEAR,
        "source_urls": _SOURCE_URLS,
        "zori_period": zori_period,
        "output_csv": csv_path.name,
        "row_count": df.height,
        "columns": [{"name": n, "dtype": str(t)} for n, t in zip(df.columns, df.dtypes)],
        "sha256": compute_sha256(csv_path),
        "steps": steps,
    }


def write_manifest(manifest: dict[str, Any], out_path: Path) -> None:
    out_path.write_text(json.dumps(manifest, indent=2, default=str))


def verify_manifest(csv_path: Path, manifest_path: Path) -> list[str]:
    drift: list[str] = []
    manifest = json.loads(manifest_path.read_text())
    if not csv_path.exists():
        return [f"missing csv: {csv_path}"]
    actual_sha = compute_sha256(csv_path)
    if actual_sha != manifest.get("sha256"):
        # Guard None: a corrupt manifest missing "sha256" should still report drift
        # (it mismatches) rather than TypeError on slicing None.
        drift.append(
            f"sha256 drift: manifest={(manifest.get('sha256') or '')[:12]}… "
            f"actual={(actual_sha or '')[:12]}…"
        )
    df = pl.read_csv(csv_path)
    if df.height != manifest.get("row_count"):
        drift.append(f"row_count drift: manifest={manifest.get('row_count')} actual={df.height}")
    manifest_cols = [c["name"] for c in manifest.get("columns", [])]
    if df.columns != manifest_cols:
        drift.append("column set/order drift")
    return drift
