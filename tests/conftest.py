"""Shared test fixtures for housing-commute-analysis."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # headless backend so report/figure tests run without a display

import calendar
import os
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _month_ends(start_year: int, start_month: int, n_months: int) -> list[date]:
    """n_months consecutive month-end dates starting at (start_year, start_month)."""
    out: list[date] = []
    year, month = start_year, start_month
    for _ in range(n_months):
        out.append(date(year, month, calendar.monthrange(year, month)[1]))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


@pytest.fixture
def sample_zcta_df() -> pl.DataFrame:
    """Minimal valid ZCTA-level DataFrame for analysis tests.

    Contains 20 rows with all columns required by load_and_validate_data()
    and the RQ analysis modules.
    """
    np.random.seed(42)
    n = 20
    return pl.DataFrame({
        "ZCTA5CE": [f"8500{i}" for i in range(n)],
        "rent_to_income": np.random.uniform(0.15, 0.55, n).tolist(),
        "commute_min_proxy": np.random.uniform(15.0, 45.0, n).tolist(),
        "median_income": np.random.uniform(30000, 120000, n).tolist(),
        "median_rent": np.random.uniform(800, 2500, n).tolist(),
        "stops_per_km2": np.random.uniform(0.0, 5.0, n).tolist(),
        "renter_share": np.random.uniform(0.2, 0.8, n).tolist(),
        "vehicle_access": np.random.uniform(0.5, 0.98, n).tolist(),
        "pop_density": np.random.uniform(100, 5000, n).tolist(),
        "total_pop": np.random.randint(1000, 50000, n).tolist(),
        "pct_white": np.random.uniform(0.1, 0.8, n).tolist(),
        "pct_black": np.random.uniform(0.05, 0.4, n).tolist(),
        "pct_hispanic": np.random.uniform(0.05, 0.5, n).tolist(),
        "pct_asian": np.random.uniform(0.01, 0.2, n).tolist(),
        "zori": np.random.uniform(900, 2800, n).tolist(),
        "long45_share": np.random.uniform(0.05, 0.35, n).tolist(),
        "pct_transit": np.random.uniform(0.0, 0.3, n).tolist(),
        "pct_drive_alone": np.random.uniform(0.4, 0.9, n).tolist(),
        "pct_car": np.random.uniform(0.5, 0.95, n).tolist(),
        "job_density": np.random.uniform(10.0, 2000.0, n).tolist(),
        "distance_to_cbd_km": np.random.uniform(1.0, 40.0, n).tolist(),
        "job_accessibility": np.random.uniform(1_000.0, 200_000.0, n).tolist(),
    })


@pytest.fixture
def sample_zcta_csv(sample_zcta_df: pl.DataFrame, tmp_path: Path) -> Path:
    """Write sample ZCTA DataFrame to a temporary CSV file.

    Returns
    -------
    Path
        Path to the temp CSV file.
    """
    csv_path = tmp_path / "final_zcta_dataset_phoenix.csv"
    sample_zcta_df.write_csv(csv_path)
    return csv_path


@pytest.fixture
def numpy_X_y() -> tuple[np.ndarray, np.ndarray]:
    """Simple X/y pair for regression model tests.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        Feature matrix (50x3) and target (50,).
    """
    np.random.seed(42)
    X = np.random.randn(50, 3)
    y = 0.5 + 1.2 * X[:, 0] - 0.8 * X[:, 1] + 0.3 * X[:, 2] + np.random.randn(50) * 0.5
    return X, y


@pytest.fixture
def sample_panel_fixtures() -> tuple[
    pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame
]:
    """Synthetic (cross_df, zori_panel, lodes_panel, acs2019) quadruple for RQ4.

    30 ZCTAs (three ZIP3 prefixes, so coarse-cluster robustness has >= 3
    clusters) x 60 months (2019-01 .. 2023-12) spanning the 2020-03 break with
    both post phases. Planted structure the RQ4 tests rely on:

    - a positive distance_to_cbd_km x Post1 donut repricing effect
      (B1 = 0.006/km on log rent) with partial persistence in Post2
      (B2 = 0.003/km);
    - 4 post-2019 entrant ZCTAs whose zori rows start 2020-06 (absent rows,
      never nulls — feeds the entrant-composition diagnostics);
    - DIFFERENT 2019 and 2021 commute-proxy vintages (acs2019 vs cross_df's
      35-column commute_min_proxy differ by 2-4 minutes everywhere) so the
      headline-vintage test can detect which one a model loads on;
    - LODES years 2015-2023 with a 2020/21 accessibility dip AND
      idiosyncratic per-(ZCTA, year) variation — without it log access is
      exactly unit-effect + common-year-factor, perfectly collinear with the
      two-way FE, and Specs C/D (Task 18) would be unidentified.

    All three panel frames pass their src.pipelines.schema validators.
    """
    rng = np.random.default_rng(4242)

    zctas = [f"{prefix}{i:02d}" for prefix in ("850", "851", "852") for i in range(1, 11)]
    n = len(zctas)
    entrants = set(zctas[-4:])  # post-2019 entrants (enter 2020-06)
    entry_month = date(2020, 6, 30)

    months = _month_ends(2019, 1, 60)
    post1_start, post1_end = date(2020, 3, 31), date(2021, 12, 31)

    # --- ZCTA-level geography and planted gradient regressors ---------------
    distance_km = rng.uniform(2.0, 40.0, n)
    proxy_2019 = np.clip(15.0 + 0.6 * distance_km + rng.normal(0.0, 3.0, n), 6.0, 90.0)
    # 2021-vintage (ACS 2017-2021) proxy: shifted 2-4 min so vintages always differ.
    proxy_2021 = np.clip(proxy_2019 + 3.0 + rng.uniform(-1.0, 1.0, n), 6.0, 95.0)

    # --- zori panel: log-linear DGP with the planted two-phase break --------
    unit_fe = -0.008 * distance_km + rng.normal(0.0, 0.05, n)
    b1, b2 = 0.006, 0.003  # per-km Post1 / Post2 repricing on log rent
    rows: dict[str, list] = {"ZCTA5CE": [], "period": [], "zori": []}
    for i, zcta in enumerate(zctas):
        for t, month in enumerate(months):
            if zcta in entrants and month < entry_month:
                continue  # entrant: absent rows before entry, never nulls
            log_rent = (
                np.log(1500.0)
                + unit_fe[i]
                + 0.004 * t  # common month effect (trend)
                + b1 * distance_km[i] * (post1_start <= month <= post1_end)
                + b2 * distance_km[i] * (month > post1_end)
                + rng.normal(0.0, 0.02)
            )
            rows["ZCTA5CE"].append(zcta)
            rows["period"].append(month.isoformat())
            rows["zori"].append(float(np.exp(log_rent)))
    zori_panel = pl.DataFrame(rows)

    # --- lodes panel: years 2015-2023, accessibility dips in 2020/21 --------
    lodes_years = list(range(2015, 2024))
    base_jobs = rng.integers(500, 40_000, n)
    base_access = np.exp(12.0 - 0.05 * distance_km + rng.normal(0.0, 0.1, n))
    lodes_rows: dict[str, list] = {
        "ZCTA5CE": [], "year": [], "job_count": [], "job_accessibility": []
    }
    for i, zcta in enumerate(zctas):
        for year in lodes_years:
            growth = 1.0 + 0.02 * (year - 2015)
            covid_dip = 0.90 if year in (2020, 2021) else 1.0
            lodes_rows["ZCTA5CE"].append(zcta)
            lodes_rows["year"].append(year)
            lodes_rows["job_count"].append(int(base_jobs[i] * growth * covid_dip))
            lodes_rows["job_accessibility"].append(
                float(
                    base_access[i]
                    * growth
                    * covid_dip
                    * np.exp(rng.normal(0.0, 0.08))  # idiosyncratic (i, y) shock
                )
            )
    lodes_panel = pl.DataFrame(lodes_rows)

    # --- ACS 2019 pre-COVID commute vintage ---------------------------------
    acs2019 = pl.DataFrame({
        "ZCTA5CE": zctas,
        "commute_min_proxy_2019": proxy_2019.tolist(),
        "ttw_total_2019": rng.integers(800, 5000, n).tolist(),
    })

    # --- 35-column cross-sectional frame (the RQ4-relevant subset) ----------
    access_2021 = (
        lodes_panel.filter(pl.col("year") == 2021)["job_accessibility"].to_list()
    )
    cross_df = pl.DataFrame({
        "ZCTA5CE": zctas,
        "distance_to_cbd_km": distance_km.tolist(),
        "commute_min_proxy": proxy_2021.tolist(),  # 2017-2021 vintage
        "job_accessibility": access_2021,  # LODES_YEAR = 2021 snapshot
        "renter_share": rng.uniform(0.2, 0.8, n).tolist(),
        "total_pop": rng.integers(1_000, 50_000, n).tolist(),
    })

    return cross_df, zori_panel, lodes_panel, acs2019


@pytest.fixture(autouse=True, scope="session")
def _prefect_offline(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Force Prefect fully offline/ephemeral for the whole test session."""
    home = tmp_path_factory.mktemp("prefect_home")
    os.environ["PREFECT_HOME"] = str(home)
    os.environ["PREFECT_RESULTS_LOCAL_STORAGE_PATH"] = str(home / "results")
    os.environ["PREFECT_SERVER_ALLOW_EPHEMERAL_MODE"] = "true"
    os.environ["PREFECT_LOGGING_LEVEL"] = "WARNING"
    os.environ.pop("PREFECT_API_URL", None)
