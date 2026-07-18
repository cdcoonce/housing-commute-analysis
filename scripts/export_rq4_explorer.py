"""Export RQ4 results to ``explorer/data/rq4.json`` for the interactive explorer.

Pure re-computation from the committed data products: loads each metro's
35-column cross-section and panel products, calls :func:`analyze_rq4`
(no report/figure I/O, so ``data/processed`` and ``figures`` are untouched),
and serializes the explorer's slice of :class:`RQ4Results` — Spec A joint +
single-interaction coefficients, wild-bootstrap p-values, the Spec B event
study, and identification metadata — into one JSON file.

Editorial content (pre-trend verdicts, per-metro readings) mirrors
``docs/findings.md`` section 10 and lives in ``EDITORIAL`` below; numbers all
come from the estimation results.

Usage:
    uv run python scripts/export_rq4_explorer.py [METRO ...]
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.data_loader import (  # noqa: E402
    METRO_FILES,
    METRO_NAMES,
    load_and_validate_data,
    load_panel_data,
)
from src.models.rq4_rent_dynamics import analyze_rq4  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

METROS = ["PHX", "LA", "DFW", "MEM", "DEN", "ATL", "CHI", "SEA", "MIA"]
FINAL_DIR = ROOT / "data" / "final"
OUT_PATH = ROOT / "explorer" / "data" / "rq4.json"

# Mirrors docs/findings.md section 10 (pre-trend verdicts + per-metro
# readings). Editorial prose, not computed — keep in sync with findings.
EDITORIAL: dict[str, dict[str, str]] = {
    "PHX": {
        "pretrend": "Drift for distance; commute borderline",
        "verdict": (
            "Moderate-confidence, persistent periphery repricing: the commute "
            "gradient repriced upward in both phases with access down in the "
            "disruption phase. Only the distance channel survives the "
            "coarse-cluster bootstrap, and its pre-path drifts."
        ),
    },
    "LA": {
        "pretrend": "Flat — the cleanest pre-path in the study",
        "verdict": (
            "Access-only repricing: rents in job-accessible ZCTAs fell "
            "relative to the covered submarket and kept falling into the "
            "return-to-office era. The coarse-cluster bootstrap narrowly "
            "misses (p ≈ 0.11–0.13)."
        ),
    },
    "DFW": {
        "pretrend": "Drift for distance and access; commute flat",
        "verdict": (
            "Access-led repricing — the study's most bootstrap-robust "
            "access result; commute itself never significant."
        ),
    },
    "MEM": {
        "pretrend": "Uninformative (7–12 identifying ZCTAs per pre-bin)",
        "verdict": (
            "Under-identified — only 12 ZCTAs observed on both sides of "
            "the break. No evidence either way."
        ),
    },
    "DEN": {
        "pretrend": "Drift for commute",
        "verdict": (
            "The strongest commute repricing of the nine, larger in the "
            "return-to-office phase; its disruption-phase commute channel "
            "survives the coarse-cluster bootstrap — but part of the rise "
            "predates COVID."
        ),
    },
    "ATL": {
        "pretrend": "Drift on all three gradients",
        "verdict": (
            "The largest coefficients in the study, all growing in the "
            "return-to-office phase — read as COVID accelerating a "
            "pre-existing periphery-ward steepening, not a clean break."
        ),
    },
    "CHI": {
        "pretrend": "Flat for commute; drift for access",
        "verdict": (
            "The cleanest commute break of the nine, nearly doubling in the "
            "return-to-office phase; the access effect fades — the "
            "study's one clear partial reversal. Nothing survives the "
            "coarse-cluster bootstrap."
        ),
    },
    "SEA": {
        "pretrend": "Strongest drift in the study",
        "verdict": (
            "Large positive distance repricing — the study's most "
            "bootstrap-robust result — but the steepest pre-trends run "
            "straight into it. Trend + break, direction periphery-favoring."
        ),
    },
    "MIA": {
        "pretrend": "Drift on all three gradients",
        "verdict": "Essentially no COVID-specific repricing.",
    },
}

VARIABLE_LABELS = {
    "commute_min_proxy_2019": "Commute time (min, 2019)",
    "distance_to_cbd_km": "Distance to CBD (km)",
    "log_job_accessibility_2019": "Log job accessibility (2019)",
}


def jsonable(obj: Any) -> Any:
    """Recursively convert results objects to JSON-serializable values."""
    if isinstance(obj, pl.DataFrame):
        return obj.to_dicts()
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (str, bool)) or obj is None:
        return obj
    if isinstance(obj, (int, float)):
        return obj
    if hasattr(obj, "item"):  # numpy scalar
        return obj.item()
    return str(obj)


def export_metro(metro: str) -> dict[str, Any]:
    csv_file = FINAL_DIR / METRO_FILES[metro]
    df = load_and_validate_data(csv_file, metro)
    zori_panel, lodes_panel, acs2019 = load_panel_data(metro, FINAL_DIR)
    r = analyze_rq4(df, zori_panel, lodes_panel, acs2019)
    return {
        "code": metro,
        "name": METRO_NAMES[metro],
        "n_obs": r.n_obs,
        "n_zctas": r.n_zctas,
        "n_identifying": r.n_identifying,
        "n_pre_months": r.n_pre_months,
        "n_post_months": r.n_post_months,
        "coverage": jsonable(r.coverage),
        "flags": list(r.flags),
        "spec_a_joint": jsonable(r.gradient_model_joint),
        "spec_a_single": jsonable(r.gradient_models_single),
        "wald_break": jsonable(r.wald_break),
        "bootstrap_pvalues": jsonable(r.bootstrap_pvalues),
        "event_study": jsonable(r.event_study),
        "editorial": EDITORIAL[metro],
    }


def main() -> int:
    metros = [m.upper() for m in sys.argv[1:]] or METROS
    unknown = [m for m in metros if m not in METROS]
    if unknown:
        logger.error("unknown metro(s): %s", unknown)
        return 1
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text()).get("metros", {})
    for metro in metros:
        logger.info("exporting %s ...", metro)
        existing[metro] = export_metro(metro)
        logger.info(
            "  %s: %d obs, %d ZCTAs, %d identifying",
            metro,
            existing[metro]["n_obs"],
            existing[metro]["n_zctas"],
            existing[metro]["n_identifying"],
        )
    payload = {
        "generated_from": "committed data products (see data/final manifests)",
        "variables": VARIABLE_LABELS,
        "metro_order": METROS,
        "metros": {m: existing[m] for m in METROS if m in existing},
    }
    OUT_PATH.write_text(json.dumps(payload, indent=1))
    logger.info("wrote %s (%.1f KB)", OUT_PATH, OUT_PATH.stat().st_size / 1024)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
