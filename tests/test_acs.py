"""Tests for src.pipelines.acs module.

Covers compute_acs_features (derived feature engineering from raw ACS data),
fetch_acs_for_county input validation, the TTW_MIDPOINTS constant, and the
ZCTA-altitude fetch_acs_commute_zcta (monkeypatched Census API).
"""

from pathlib import Path

import pandas as pd
import pytest
import requests

import src.pipelines.acs as acs
from src.pipelines.acs import (
    TTW_MIDPOINTS,
    compute_acs_features,
    fetch_acs_commute_zcta,
    fetch_acs_for_county,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def raw_acs_df() -> pd.DataFrame:
    """Small DataFrame of realistic raw ACS data (4 rows) for compute_acs_features tests.

    Values are positive integers typical of census tract-level ACS estimates.
    """
    data = {
        "GEOID": ["04013100100", "04013100200", "04013100300", "04013100400"],
        "year": [2021, 2021, 2021, 2021],
        "median_rent": [1200, 950, 1500, 1100],
        "median_income": [60000, 45000, 80000, 55000],
        # Travel time to work bins (workers counts)
        "ttw_total": [500, 400, 600, 350],
        "ttw_lt5": [20, 15, 10, 25],
        "ttw_5_9": [30, 25, 20, 30],
        "ttw_10_14": [50, 40, 30, 35],
        "ttw_15_19": [60, 50, 50, 40],
        "ttw_20_24": [80, 60, 70, 50],
        "ttw_25_29": [50, 40, 60, 30],
        "ttw_30_34": [70, 55, 80, 45],
        "ttw_35_39": [40, 30, 50, 25],
        "ttw_40_44": [30, 25, 40, 20],
        "ttw_45_59": [40, 30, 80, 25],
        "ttw_60_89": [20, 20, 70, 15],
        "ttw_90_plus": [10, 10, 40, 10],
        # Mode of transportation
        "mode_total": [500, 400, 600, 350],
        "mode_car_alone": [350, 280, 360, 250],
        "mode_carpool": [50, 40, 60, 30],
        "mode_transit": [30, 25, 80, 20],
        "mode_walk": [20, 15, 30, 15],
        "mode_other": [10, 10, 20, 10],
        "mode_wfh": [40, 30, 50, 25],
        # Rent burden
        "rent_burden_total": [200, 180, 250, 150],
        "rent_burden_30_34": [30, 25, 35, 20],
        "rent_burden_35_39": [20, 18, 25, 15],
        "rent_burden_40_49": [25, 20, 30, 18],
        "rent_burden_50_plus": [35, 30, 50, 25],
        # Tenure
        "tenure_total": [400, 350, 500, 300],
        "tenure_owner": [240, 200, 280, 170],
        "tenure_renter": [160, 150, 220, 130],
        # Vehicles
        "vehicles_total": [400, 350, 500, 300],
        "vehicles_none": [20, 15, 40, 10],
        "vehicles_1": [150, 130, 180, 110],
        "vehicles_2_plus": [230, 205, 280, 180],
    }
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# compute_acs_features
# ---------------------------------------------------------------------------


class TestComputeAcsFeatures:
    """Tests for the compute_acs_features function."""

    def test_compute_acs_features_commute_proxy(
        self, raw_acs_df: pd.DataFrame
    ) -> None:
        """commute_min_proxy should be a weighted average in the plausible range [0, 90]."""
        result = compute_acs_features(raw_acs_df)

        assert "commute_min_proxy" in result.columns
        for value in result["commute_min_proxy"]:
            assert 0 <= value <= 90, (
                f"commute_min_proxy {value} outside plausible range [0, 90]"
            )

    def test_compute_acs_features_rent_to_income(
        self, raw_acs_df: pd.DataFrame
    ) -> None:
        """rent_to_income should equal median_rent / (median_income / 12)."""
        result = compute_acs_features(raw_acs_df)

        assert "rent_to_income" in result.columns
        for _, row in result.iterrows():
            expected = row["median_rent"] / (row["median_income"] / 12.0)
            assert row["rent_to_income"] == pytest.approx(expected, rel=1e-9)

    def test_compute_acs_features_mode_shares_sum(
        self, raw_acs_df: pd.DataFrame
    ) -> None:
        """Mode share percentages should approximately sum to 100 when all modes are included."""
        result = compute_acs_features(raw_acs_df)

        mode_cols = [
            "pct_drive_alone",
            "pct_carpool",
            "pct_transit",
            "pct_walk",
            "pct_wfh",
        ]
        for _, row in result.iterrows():
            # mode_other is not given its own pct column, so the five named
            # shares will sum to less than 100 by the "other" proportion.
            mode_sum = sum(row[col] for col in mode_cols)
            other_pct = (row["mode_other"] / row["mode_total"]) * 100
            assert mode_sum + other_pct == pytest.approx(100.0, abs=0.01)

    def test_compute_acs_features_negative_handled(
        self, raw_acs_df: pd.DataFrame
    ) -> None:
        """Census null codes (negative values) should be replaced with NaN."""
        df = raw_acs_df.copy()
        # Inject Census null codes into the first row
        df.loc[0, "median_rent"] = -666666666
        df.loc[0, "median_income"] = -666666666

        result = compute_acs_features(df)

        assert pd.isna(result.loc[0, "median_rent"])
        assert pd.isna(result.loc[0, "median_income"])
        assert pd.isna(result.loc[0, "rent_to_income"])

    def test_compute_acs_features_pct_car_sum(
        self, raw_acs_df: pd.DataFrame
    ) -> None:
        """pct_car should equal pct_drive_alone + pct_carpool."""
        result = compute_acs_features(raw_acs_df)

        for _, row in result.iterrows():
            expected = row["pct_drive_alone"] + row["pct_carpool"]
            assert row["pct_car"] == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# fetch_acs_for_county — input validation
# ---------------------------------------------------------------------------


class TestFetchAcsValidation:
    """Tests for fetch_acs_for_county input validation."""

    def test_fetch_acs_invalid_fips(self) -> None:
        """Non-numeric or wrong-length state FIPS should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid state FIPS"):
            fetch_acs_for_county(state_fips="X", county_fips="013", year=2021)

    def test_fetch_acs_invalid_year(self) -> None:
        """A year not in AVAILABLE_ACS_YEARS should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid ACS year"):
            fetch_acs_for_county(state_fips="04", county_fips="013", year=2020)


# ---------------------------------------------------------------------------
# TTW_MIDPOINTS extraction (Task 10) — refactor must be output-invariant
# ---------------------------------------------------------------------------


class TestTtwMidpoints:
    """Tests for the extracted TTW_MIDPOINTS module constant."""

    def test_ttw_midpoints_twelve_bins_expected_values(self) -> None:
        """The 12 B08303 bin midpoints, exactly as previously inlined."""
        assert TTW_MIDPOINTS == {
            "ttw_lt5": 2.5,
            "ttw_5_9": 7.0,
            "ttw_10_14": 12.0,
            "ttw_15_19": 17.0,
            "ttw_20_24": 22.0,
            "ttw_25_29": 27.0,
            "ttw_30_34": 32.0,
            "ttw_35_39": 37.0,
            "ttw_40_44": 42.0,
            "ttw_45_59": 52.0,
            "ttw_60_89": 75.0,
            "ttw_90_plus": 100.0,
        }
        assert "ttw_total" not in TTW_MIDPOINTS  # universe is not a bin

    def test_compute_acs_features_matches_pre_refactor_golden(
        self, raw_acs_df: pd.DataFrame
    ) -> None:
        """Byte-identical output to the golden snapshot generated from the
        PRE-refactor inline-midpoint code (same discipline as the ZORI golden).
        """
        got = compute_acs_features(raw_acs_df).to_csv(index=False)
        golden = (FIXTURES / "acs_features_golden.csv").read_text()
        assert got == golden


# ---------------------------------------------------------------------------
# fetch_acs_commute_zcta — monkeypatched Census API JSON responses
# ---------------------------------------------------------------------------


# B08303 API codes in table order: 001E = total, 002E..013E = the 12 bins.
_B08303_CODES = [f"B08303_{i:03d}E" for i in range(1, 14)]

# Two live ZCTAs (one short code to exercise zero-padding) + one zero-worker.
#                 total lt5 5-9 10-14 15-19 20-24 25-29 30-34 35-39 40-44 45-59 60-89 90+
_ZCTA_COUNTS = {
    "85001": [100, 10, 0, 20, 0, 30, 0, 40, 0, 0, 0, 0, 0],
    "601": [4, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "85002": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
}


def _b08303_payload(nested: bool) -> list[list[str]]:
    """Fake Census API JSON: header row + one row per ZCTA (string cells)."""
    geo_cols = ["state", "zip code tabulation area"] if nested else [
        "zip code tabulation area"
    ]
    header = _B08303_CODES + geo_cols
    rows = []
    for zcta, counts in _ZCTA_COUNTS.items():
        geo = ["04", zcta] if nested else [zcta]
        rows.append([str(c) for c in counts] + geo)
    return [header] + rows


class _FakeResponse:
    def __init__(self, payload=None, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error")


class _FakeSession:
    """Returns queued responses in order; records every (url, params) call."""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def get(self, url: str, params=None, timeout=None) -> _FakeResponse:
        self.calls.append({"url": url, "params": dict(params or {})})
        return self._responses.pop(0)


def _expected_proxy(zcta: str) -> float:
    counts = _ZCTA_COUNTS[zcta]
    total, bins = counts[0], counts[1:]
    return sum(
        count * midpoint
        for count, midpoint in zip(bins, TTW_MIDPOINTS.values())
    ) / total


class TestFetchAcsCommuteZcta:
    """Tests for the ZCTA-altitude B08303 fetch (Task 10)."""

    def test_state_nested_query_proxy_and_dtypes(self, monkeypatch) -> None:
        """proxy = sum(count x midpoint) / total via TTW_MIDPOINTS; ZCTA5CE
        zero-padded; ttw_total int."""
        session = _FakeSession([_FakeResponse(_b08303_payload(nested=True))])
        monkeypatch.setattr(acs, "_get_session", lambda: session)

        out = fetch_acs_commute_zcta("04", 2019)

        assert len(session.calls) == 1
        assert session.calls[0]["params"]["in"] == "state:04"
        assert session.calls[0]["params"]["for"] == "zip code tabulation area:*"
        assert "2019" in session.calls[0]["url"]

        assert list(out.columns) == ["ZCTA5CE", "commute_min_proxy", "ttw_total"]
        assert set(out["ZCTA5CE"]) == {"85001", "00601"}  # zero-padded
        assert out["ttw_total"].dtype.kind == "i"

        by_zcta = out.set_index("ZCTA5CE")
        assert by_zcta.loc["85001", "commute_min_proxy"] == pytest.approx(
            _expected_proxy("85001")
        )
        assert by_zcta.loc["85001", "commute_min_proxy"] == pytest.approx(22.05)
        assert by_zcta.loc["00601", "commute_min_proxy"] == pytest.approx(2.5)
        assert by_zcta.loc["85001", "ttw_total"] == 100

        # stable-sorted by ZCTA5CE (issue #6 convention)
        assert list(out["ZCTA5CE"]) == sorted(out["ZCTA5CE"])

    def test_zero_worker_zcta_dropped(self, monkeypatch) -> None:
        """ttw_total == 0 must not divide-by-zero; the row is dropped
        (mirrors the existing replace(0, NA) guard in compute_acs_features)."""
        session = _FakeSession([_FakeResponse(_b08303_payload(nested=True))])
        monkeypatch.setattr(acs, "_get_session", lambda: session)

        out = fetch_acs_commute_zcta("04", 2019)

        assert "85002" not in set(out["ZCTA5CE"])
        assert out["commute_min_proxy"].notna().all()

    def test_national_fallback_when_state_nesting_rejected(
        self, monkeypatch
    ) -> None:
        """HTTP 400 on the state-nested form falls back to the national pull
        (no `in` clause) — design 'Data availability' documented fallback."""
        session = _FakeSession(
            [
                _FakeResponse(status_code=400),
                _FakeResponse(_b08303_payload(nested=False)),
            ]
        )
        monkeypatch.setattr(acs, "_get_session", lambda: session)

        out = fetch_acs_commute_zcta("04", 2019)

        assert len(session.calls) == 2
        assert "in" in session.calls[0]["params"]
        assert "in" not in session.calls[1]["params"]
        assert set(out["ZCTA5CE"]) == {"85001", "00601"}

    def test_non_400_error_raises_loudly(self, monkeypatch) -> None:
        """A 404 (bad year/dataset) is not a nesting rejection — no fallback."""
        session = _FakeSession([_FakeResponse(status_code=404)])
        monkeypatch.setattr(acs, "_get_session", lambda: session)

        with pytest.raises(requests.HTTPError):
            fetch_acs_commute_zcta("04", 2019)
        assert len(session.calls) == 1

    def test_invalid_inputs_raise_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid state FIPS"):
            fetch_acs_commute_zcta("X", 2019)
        with pytest.raises(ValueError, match="Invalid ACS year"):
            fetch_acs_commute_zcta("04", 2020)
