"""Gate matrix for panel_gate.py (offline; frames built inline)."""
from __future__ import annotations

import pandas as pd

from scripts.panel_gate import (
    check_acs_commute_2019,
    check_lodes_panel,
    check_lodes_sanity,
    check_zori_panel,
)


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


# --- LODES panel: append-only, int byte-identity, float rtol (plan Task 12) ---


def _lodes(cells: list[tuple[str, int, int, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        cells, columns=["ZCTA5CE", "year", "job_count", "job_accessibility"]
    )


LODES_BASE = _lodes([
    ("85001", 2015, 100, 5000.0), ("85001", 2016, 110, 5100.0),
    ("85002", 2015, 200, 4000.0), ("85002", 2016, 210, 4100.0),
])


def test_lodes_identical_passes_with_zero_max_delta() -> None:
    r = check_lodes_panel(LODES_BASE, LODES_BASE.copy())
    assert r.ok
    assert r.revision_report["access_max_rel_delta"] == 0.0


def test_lodes_job_count_change_fails_under_every_accept_flag() -> None:
    """A job_count change on an existing cell means an upstream reissue and
    must be investigated — design §3 grants it NO escape hatch."""
    new = LODES_BASE.copy()
    new.loc[0, "job_count"] += 1
    r = check_lodes_panel(LODES_BASE, new)
    assert not r.ok and any("job_count" in e for e in r.errors)
    r_hatched = check_lodes_panel(LODES_BASE, new, accept_access_drift=True)
    assert not r_hatched.ok and any("job_count" in e for e in r_hatched.errors)


def test_lodes_access_float_noise_passes_and_reports_max_delta() -> None:
    new = LODES_BASE.copy()
    new.loc[0, "job_accessibility"] *= 1 + 1e-13     # < FLOAT_NOISE_RTOL
    r = check_lodes_panel(LODES_BASE, new)
    assert r.ok
    assert 0.0 < r.revision_report["access_max_rel_delta"] < 1e-12


def test_lodes_access_drift_fails_then_accept_access_drift_passes() -> None:
    new = LODES_BASE.copy()
    new.loc[0, "job_accessibility"] *= 1 + 1e-6      # > FLOAT_NOISE_RTOL
    r = check_lodes_panel(LODES_BASE, new)
    assert not r.ok and any("job_accessibility" in e for e in r.errors)
    r_hatched = check_lodes_panel(LODES_BASE, new, accept_access_drift=True)
    assert r_hatched.ok and r_hatched.waived


def test_lodes_new_year_appended_at_tail_passes() -> None:
    appended = pd.concat(
        [LODES_BASE, _lodes([("85001", 2017, 120, 5200.0), ("85002", 2017, 220, 4200.0)])],
        ignore_index=True,
    )
    assert check_lodes_panel(LODES_BASE, appended).ok


def test_lodes_removed_year_fails() -> None:
    new = LODES_BASE[LODES_BASE["year"] != 2016]
    r = check_lodes_panel(LODES_BASE, new)
    assert not r.ok and any("year" in e for e in r.errors)


def test_lodes_new_year_before_tail_fails() -> None:
    """Append-only means the TAIL: a year materializing before the baseline
    max is a history rewrite, not an append."""
    new = pd.concat(
        [LODES_BASE, _lodes([("85001", 2014, 90, 4900.0), ("85002", 2014, 190, 3900.0)])],
        ignore_index=True,
    )
    r = check_lodes_panel(LODES_BASE, new)
    assert not r.ok and any("tail" in e for e in r.errors)


def test_lodes_removed_cell_within_kept_year_fails() -> None:
    new = LODES_BASE.drop(index=[1])                 # 85001/2016 gone, year kept
    r = check_lodes_panel(LODES_BASE, new)
    assert not r.ok and any("cell" in e for e in r.errors)


# --- ACS 2019: frozen vintage — int byte-identity, proxy at rtol, no hatch ---


def _acs(rows: list[tuple[str, float, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows, columns=["ZCTA5CE", "commute_min_proxy_2019", "ttw_total_2019"]
    )


ACS_BASE = _acs([("85001", 25.5, 800), ("85002", 30.1, 900)])


def test_acs_identical_passes() -> None:
    assert check_acs_commute_2019(ACS_BASE, ACS_BASE.copy()).ok


def test_acs_proxy_float_noise_passes_with_report() -> None:
    new = ACS_BASE.copy()
    new.loc[0, "commute_min_proxy_2019"] *= 1 + 1e-13
    r = check_acs_commute_2019(ACS_BASE, new)
    assert r.ok
    assert 0.0 < r.revision_report["proxy_max_rel_delta"] < 1e-12


def test_acs_proxy_drift_fails_no_hatch() -> None:
    new = ACS_BASE.copy()
    new.loc[0, "commute_min_proxy_2019"] *= 1.001
    r = check_acs_commute_2019(ACS_BASE, new)
    assert not r.ok and any("commute_min_proxy_2019" in e for e in r.errors)


def test_acs_ttw_total_change_fails() -> None:
    new = ACS_BASE.copy()
    new.loc[0, "ttw_total_2019"] += 1
    r = check_acs_commute_2019(ACS_BASE, new)
    assert not r.ok and any("ttw_total_2019" in e for e in r.errors)


def test_acs_zcta_set_change_fails() -> None:
    """A frozen Census vintage does not gain or lose rows — either direction
    means our query or code-match changed."""
    assert not check_acs_commute_2019(ACS_BASE, ACS_BASE.iloc[[0]].copy()).ok
    grown = pd.concat([ACS_BASE, _acs([("85003", 28.0, 700)])], ignore_index=True)
    assert not check_acs_commute_2019(ACS_BASE, grown).ok


# --- LODES new-data sanity: gradient sign + log-transform guard (design §3) ---


_SANITY_CROSS = pd.DataFrame({
    "ZCTA5CE": ["85001", "85002", "85003", "85004"],
    "distance_to_cbd_km": [1.0, 5.0, 10.0, 20.0],
})


def _sanity_panel(access: list[float]) -> pd.DataFrame:
    return _lodes([
        (z, 2015, 100, a)
        for z, a in zip(["85001", "85002", "85003", "85004"], access)
    ])


def test_lodes_sanity_negative_gradient_passes() -> None:
    assert check_lodes_sanity(_sanity_panel([9000.0, 7000.0, 5000.0, 3000.0]),
                              _SANITY_CROSS) == []


def test_lodes_sanity_positive_gradient_fails_per_year() -> None:
    errors = check_lodes_sanity(_sanity_panel([3000.0, 5000.0, 7000.0, 9000.0]),
                                _SANITY_CROSS)
    assert any("Spearman" in e and "2015" in e for e in errors)


def test_lodes_sanity_nonpositive_access_fails() -> None:
    errors = check_lodes_sanity(_sanity_panel([9000.0, 7000.0, 5000.0, 0.0]),
                                _SANITY_CROSS)
    assert any("job_accessibility" in e for e in errors)
