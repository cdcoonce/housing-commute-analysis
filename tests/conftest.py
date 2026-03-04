"""Shared test fixtures for housing-commute-analysis."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


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
