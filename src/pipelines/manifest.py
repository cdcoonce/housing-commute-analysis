"""Provenance manifest for final datasets: sha256 + schema + source vintages."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import polars as pl

from src.pipelines.acs import DEFAULT_ACS_YEAR  # ACS commute vintage (2021)
from src.pipelines.config import METRO_CONFIGS, ZORI_PANEL_CSV_URL, ZORI_ZIP_CSV_URL
from src.pipelines.lodes import LODES_YEAR
from src.pipelines.tiger import CBSA_VINTAGE  # pinned CBSA delineation vintage

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


PROVENANCE_PIPELINE_BUILD = "pipeline-build"
PROVENANCE_REGENERATED_OFFLINE = "regenerated-offline"
_PROVENANCE_MODES = (PROVENANCE_PIPELINE_BUILD, PROVENANCE_REGENERATED_OFFLINE)


def build_manifest(
    metro_key: str,
    csv_path: Path,
    *,
    git_commit: str,
    timestamp_utc: str,
    zori_period: str | None,
    steps: list[dict[str, Any]],
    provenance: str = PROVENANCE_PIPELINE_BUILD,
) -> dict[str, Any]:
    """Build a provenance manifest for a final CSV.

    ``provenance`` distinguishes how the manifest came to exist (issue #3):

    - ``"pipeline-build"`` (default): the pipeline built the data at
      ``git_commit``, which is stamped as the build commit.
    - ``"regenerated-offline"``: the manifest was rewritten from an existing
      CSV the pipeline did NOT build at the current commit. ``git_commit`` is
      recorded as null (no build commit can honestly be claimed) and the
      stamping commit lands in ``regenerated_at_commit`` instead. This routing
      happens here, not at call sites, so an offline caller cannot stamp false
      build provenance even by passing the current commit.
    """
    if provenance not in _PROVENANCE_MODES:
        raise ValueError(
            f"unknown provenance mode {provenance!r}; expected one of {_PROVENANCE_MODES}"
        )
    is_build = provenance == PROVENANCE_PIPELINE_BUILD
    df = pl.read_csv(csv_path)
    return {
        "metro_key": metro_key,
        "metro_config": _metro_config_snapshot(metro_key),
        "provenance": provenance,
        "git_commit": git_commit if is_build else None,
        "regenerated_at_commit": None if is_build else git_commit,
        "run_timestamp_utc": timestamp_utc,
        "acs_commute_year": DEFAULT_ACS_YEAR,
        "acs_demographics_year": _DEMOGRAPHICS_YEAR,
        "lodes_year": LODES_YEAR,
        "cbsa_vintage": CBSA_VINTAGE,
        "source_urls": _SOURCE_URLS,
        "zori_period": zori_period,
        "output_csv": csv_path.name,
        "row_count": df.height,
        "columns": [{"name": n, "dtype": str(t)} for n, t in zip(df.columns, df.dtypes)],
        "sha256": compute_sha256(csv_path),
        "steps": steps,
    }


_PANEL_KINDS = ("zori_panel", "lodes_panel", "acs_commute_2019")
_ACS_COMMUTE_2019_YEAR = 2019  # frozen pre-COVID vintage (ACS 5-year 2015-2019)


def _panel_source_urls(kind: str, extra: dict[str, Any]) -> dict[str, str]:
    """Kind-parameterized source provenance (design §3 Manifests).

    Never reuses _SOURCE_URLS verbatim: its lodes entry interpolates
    LODES_YEAR (2021), which would stamp self-contradictory provenance
    ("WAC 2021") beside an explicit multi-year ``years`` list.
    """
    tiger = _SOURCE_URLS["tiger"]  # metro ZCTA set comes from the shared geo tasks
    if kind == "zori_panel":
        return {"zori": ZORI_PANEL_CSV_URL, "tiger": tiger}
    if kind == "lodes_panel":
        years = extra["years"]
        return {
            "lodes": (
                "https://lehd.ces.census.gov/data/lodes/LODES8 "
                f"(WAC S000_JT00 {years[0]}–{years[-1]} + xwalk)"
            ),
            "tiger": tiger,
        }
    # acs_commute_2019
    return {
        "acs": f"https://api.census.gov/data/{_ACS_COMMUTE_2019_YEAR}/acs/acs5",
        "tiger": tiger,
    }


def build_panel_manifest(
    metro_key: str,
    csv_path: Path,
    kind: str,
    *,
    git_commit: str,
    timestamp_utc: str,
    extra: dict[str, Any],
    provenance: str = PROVENANCE_PIPELINE_BUILD,
) -> dict[str, Any]:
    """Provenance manifest for an RQ4 panel data product (design §3 Manifests).

    Reuses the 35-column manifest machinery (compute_sha256,
    _metro_config_snapshot, provenance-mode routing, cbsa_vintage) but
    parameterizes source provenance per ``kind``:

    - ``"zori_panel"`` — the smoothed non-SA panel URL; adds
      period_min/period_max/n_months/n_zctas computed from the CSV
      (``pull_timestamp_utc`` arrives via ``extra`` — only the producing
      flow knows it).
    - ``"lodes_panel"`` — the LODES8 URL pattern parameterized by
      ``extra["years"]`` (required), never the stale single-year string.
    - ``"acs_commute_2019"`` — the frozen ACS 2019 5-year vintage.

    ``extra`` keys land at the manifest top level (years, pull_timestamp_utc,
    ...). The 35-column build_manifest path is untouched.
    """
    if kind not in _PANEL_KINDS:
        raise ValueError(f"unknown panel kind {kind!r}; expected one of {_PANEL_KINDS}")
    if kind == "lodes_panel" and "years" not in extra:
        raise ValueError("lodes_panel manifests require extra['years'] (explicit vintage list)")
    if provenance not in _PROVENANCE_MODES:
        raise ValueError(
            f"unknown provenance mode {provenance!r}; expected one of {_PROVENANCE_MODES}"
        )
    is_build = provenance == PROVENANCE_PIPELINE_BUILD
    df = pl.read_csv(csv_path)
    manifest: dict[str, Any] = {
        "metro_key": metro_key,
        "kind": kind,
        "metro_config": _metro_config_snapshot(metro_key),
        "provenance": provenance,
        "git_commit": git_commit if is_build else None,
        "regenerated_at_commit": None if is_build else git_commit,
        "run_timestamp_utc": timestamp_utc,
        "cbsa_vintage": CBSA_VINTAGE,
        "source_urls": _panel_source_urls(kind, extra),
        "output_csv": csv_path.name,
        "row_count": df.height,
        "columns": [{"name": n, "dtype": str(t)} for n, t in zip(df.columns, df.dtypes)],
        "sha256": compute_sha256(csv_path),
    }
    if kind == "zori_panel":
        periods = df["period"]
        manifest.update(
            period_min=str(periods.min()),
            period_max=str(periods.max()),
            n_months=periods.n_unique(),
            n_zctas=df["ZCTA5CE"].n_unique(),
        )
    manifest.update(extra)
    return manifest


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
