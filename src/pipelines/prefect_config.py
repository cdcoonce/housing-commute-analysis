"""Local-only Prefect result storage + retry/cache constants for pipeline flows.

Keeps all Prefect state inside the repo (gitignored .prefect_cache/) so runs are
resumable within the cache window without any server, agent, or deployment.

NOTE: result storage is set via the PREFECT_RESULTS_LOCAL_STORAGE_PATH env var,
NOT by passing a LocalFileSystem block to @task. Prefect 3.x raises
`TypeError: Result storage configuration must be persisted server-side` if you
pass an unsaved block as result_storage — verified against prefect 3.6.4. The env
var points result persistence at .prefect_cache/ with no server and no .save().
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = PROJECT_ROOT / ".prefect_cache"
RESULT_DIR.mkdir(parents=True, exist_ok=True)

# Direct Prefect's local result storage at the repo-local cache dir (default
# pickle serializer handles GeoDataFrames/DataFrames). setdefault so an explicit
# env override still wins.
os.environ.setdefault("PREFECT_RESULTS_LOCAL_STORAGE_PATH", str(RESULT_DIR))

CACHE_TTL = timedelta(days=7)

# Whole-step retry schedule for flaky external APIs (composes above utils.py's
# per-request urllib3 adapter retry).
NETWORK_RETRIES = {"retries": 3, "retry_delay_seconds": [5, 15, 45]}
