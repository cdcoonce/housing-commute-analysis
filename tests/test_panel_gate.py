"""Gate matrix for panel_gate.py (offline; frames built inline)."""
from __future__ import annotations

import pandas as pd

from scripts.panel_gate import check_zori_panel


def _panel(cells: list[tuple[str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(cells, columns=["ZCTA5CE", "period", "zori"])


BASE = _panel([
    ("85001", "2020-01-31", 1500.0), ("85001", "2020-02-29", 1510.0),
    ("85002", "2020-01-31", 1200.0), ("85002", "2020-02-29", 1210.0),
])


def test_identical_passes() -> None:
    assert check_zori_panel(BASE, BASE.copy()).ok


def test_lost_month_fails() -> None:
    new = BASE[BASE["period"] != "2020-02-29"]
    r = check_zori_panel(BASE, new)
    assert not r.ok and any("month" in e for e in r.errors)


def test_small_revision_passes_with_report() -> None:
    new = BASE.copy()
    new.loc[0, "zori"] *= 1.001                      # 0.1% « 5% tolerance
    r = check_zori_panel(BASE, new)
    assert r.ok and r.revision_report["n_revised"] == 1


def test_single_cell_over_25pct_fails() -> None:
    new = BASE.copy()
    new.loc[0, "zori"] *= 1.30
    assert not check_zori_panel(BASE, new).ok


def test_churned_zcta_cells_do_not_count_as_lost_cells() -> None:
    """Design §3 check 4: lost-cells over the INTERSECTION ZCTA set only —
    churn that check 3 permits must not mechanically trip check 4."""
    new = BASE[BASE["ZCTA5CE"] != "85002"]           # 50% churn: fails check 3...
    r = check_zori_panel(BASE, new)
    assert any("churn" in e for e in r.errors)
    assert not any("lost cells" in e for e in r.errors)   # ...but NOT check 4


def test_accept_structural_waives_churn_not_schema() -> None:
    new = BASE[BASE["ZCTA5CE"] != "85002"]
    assert check_zori_panel(BASE, new, accept_structural=True).ok
    bad = BASE.copy()
    bad["zori"] = -1.0                               # schema: no bypass, ever
    assert not check_zori_panel(BASE, bad, accept_structural=True).ok


def test_duplicate_key_fails() -> None:
    dup = pd.concat([BASE, BASE.iloc[[0]]], ignore_index=True)
    r = check_zori_panel(BASE, dup)
    assert not r.ok and any("duplicate" in e for e in r.errors)


def test_revised_cells_over_1pct_fails_then_accept_revisions_passes() -> None:
    """>1% of overlapping cells revised beyond the 5% tolerance FAILS; the
    reviewed-human-only accept_revisions hatch waives exactly that check."""
    new = BASE.copy()
    new.loc[0, "zori"] *= 1.10                       # 10% > 5% tol on 25% of cells
    assert not check_zori_panel(BASE, new).ok
    assert check_zori_panel(BASE, new, accept_revisions=True).ok
