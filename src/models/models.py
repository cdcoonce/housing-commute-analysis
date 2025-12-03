"""
Statistical modeling utilities for regression analysis.

This module provides functions for fitting OLS models with robust
standard errors, cross-validation, and model evaluation.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import KFold
from statsmodels.regression.quantile_regression import QuantReg
from statsmodels.stats.outliers_influence import variance_inflation_factor as vif_calc

logger = logging.getLogger(__name__)


def fit_ols_robust(
    endog: np.ndarray,
    exog: np.ndarray,
    feature_names: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Fit OLS regression with HC3 robust standard errors (heteroscedasticity-consistent).
    
    Automatically adds a constant term to the design matrix. Uses robust covariance
    estimator to correct for heteroscedastic errors without assuming constant variance.
    
    Parameters
    ----------
    endog : np.ndarray
        Dependent variable (1D array of shape (n_samples,)).
    exog : np.ndarray
        Independent variables (2D array of shape (n_samples, n_features)).
        Constant term will be added automatically.
    feature_names : Optional[List[str]], default=None
        Names of features for labeling. If None, uses generic names (x0, x1, ...).
    
    Returns
    -------
    Dict[str, Any]
        Dictionary containing:
        - 'results': statsmodels OLS results object
        - 'adj_r2': adjusted R-squared (float)
        - 'aic': Akaike Information Criterion (float)
        - 'bic': Bayesian Information Criterion (float)
        - 'params': coefficient estimates (np.ndarray)
        - 'pvalues': p-values for coefficients (np.ndarray)
        - 'std_errors': robust standard errors (np.ndarray)
        - 'feature_names': list of feature names including 'const' prefix
    
    Raises
    ------
    ValueError
        If endog and exog have incompatible shapes (mismatched sample sizes).
    
    Notes
    -----
    HC3 robust standard errors (MacKinnon & White, 1985) provide better
    small-sample properties than HC0/HC1 in the presence of influential observations.
    """
    # Validate input shapes to catch dimension mismatches early
    if endog.shape[0] != exog.shape[0]:
        raise ValueError(
            f"Sample size mismatch: endog has {endog.shape[0]} samples, "
            f"exog has {exog.shape[0]} samples. "
            "Ensure both arrays come from the same filtered dataset."
        )
    # Validate minimum sample size for regression (rule of thumb: n > 10*k)
    min_samples = 20 if exog.ndim == 1 else exog.shape[1] * 10
    if endog.shape[0] < min_samples:
        logger.warning(
            f"Sample size ({endog.shape[0]}) is small for {exog.shape[1] if exog.ndim > 1 else 1} features. "
            f"Recommend at least {min_samples} samples for stable estimates."
        )
    # Add constant term to design matrix for intercept estimation
    exog_const = sm.add_constant(exog)
    
    # Fit model with HC3 robust standard errors
    model = sm.OLS(endog, exog_const)
    results = model.fit(cov_type='HC3')
    
    # Extract metrics
    output = {
        'results': results,
        'adj_r2': results.rsquared_adj,
        'aic': results.aic,
        'bic': results.bic,
        'params': results.params,
        'pvalues': results.pvalues,
        'std_errors': results.bse,
        'feature_names': ['const'] + (feature_names if feature_names else [f'x{i}' for i in range(exog.shape[1])])
    }
    
    return output


def cv_rmse(X: np.ndarray, y: np.ndarray, k: int = 3) -> Tuple[float, List[float]]:
    """
    Compute k-fold cross-validation RMSE for an OLS model using median aggregation.

    Performs stratified k-fold cross-validation with shuffling for robust
    out-of-sample performance estimation. Returns median RMSE across folds
    to reduce sensitivity to outlier folds.

    Parameters
    ----------
    X : np.ndarray
        Feature matrix (n_samples, n_features).
    y : np.ndarray
        Target vector (n_samples,).
    k : int, optional
        Number of folds for cross-validation (default=3). Must be ≥ 2.

    Returns
    -------
    Tuple[float, List[float]]
        - Median RMSE across folds (float)
        - List of individual fold RMSEs (List[float])
    
    Raises
    ------
    ValueError
        If k < 2 or if X and y have incompatible shapes.
    
    Notes
    -----
    Uses random_state=42 for reproducibility. Constant term is force-added
    to each fold to handle standardized data where constant detection may fail.
    """
    # Validate cross-validation parameters to fail fast
    if k < 2:
        raise ValueError(
            f"Number of folds must be at least 2, got k={k}. "
            "Common values are k=3 for small samples or k=5-10 for larger samples."
        )
    if X.shape[0] != y.shape[0]:
        raise ValueError(
            f"Sample size mismatch: X has {X.shape[0]} samples, "
            f"y has {y.shape[0]} samples. Arrays must have matching first dimension."
        )
    if X.shape[0] < k:
        raise ValueError(
            f"Sample size ({X.shape[0]}) is smaller than number of folds (k={k}). "
            f"Reduce k to at most {X.shape[0]} or provide more data."
        )
    kf = KFold(n_splits=k, shuffle=True, random_state=42)
    rmses = []
    
    for train_idx, test_idx in kf.split(X):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        
        # Add constant and fit - force add to avoid detection issues with standardized data
        X_train_const = sm.add_constant(X_train, has_constant='add')
        X_test_const = sm.add_constant(X_test, has_constant='add')
        
        model = sm.OLS(y_train, X_train_const).fit()
        y_pred = model.predict(X_test_const)
        
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        rmses.append(rmse)
    
    # Return median RMSE for robustness to outlier folds
    return float(np.median(rmses)), rmses


def calculate_vif(X: np.ndarray, feature_names: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Calculate Variance Inflation Factor (VIF) for each feature to detect multicollinearity.
    
    VIF quantifies the severity of multicollinearity in regression. Values > 10
    indicate problematic multicollinearity that can inflate standard errors and
    make coefficient estimates unstable.
    
    Parameters
    ----------
    X : np.ndarray
        Feature matrix (n_samples, n_features). Should NOT include constant term.
    feature_names : Optional[List[str]], default=None
        Names of features for labeling. If None, uses generic names (x0, x1, ...).
    
    Returns
    -------
    pd.DataFrame
        DataFrame with columns ['Feature', 'VIF'], sorted by VIF descending.
        Higher VIF indicates greater multicollinearity.
    
    Notes
    -----
    VIF interpretation:
    - VIF = 1: No correlation with other predictors
    - 1 < VIF < 5: Moderate correlation, generally acceptable
    - 5 < VIF < 10: High correlation, investigate further
    - VIF > 10: Severe multicollinearity, consider removing or combining features
    
    The constant term is added internally for VIF calculation but not reported
    since its VIF is undefined (perfect collinearity with intercept).
    """
    # Add constant for proper VIF calculation
    X_const = sm.add_constant(X, has_constant='add')
    
    # Calculate VIF for each feature (skip constant at index 0)
    vif_data = []
    for i in range(1, X_const.shape[1]):  # Start at 1 to skip constant
        vif_value = vif_calc(X_const, i)
        feature_name = feature_names[i - 1] if feature_names else f'x{i - 1}'
        vif_data.append({'Feature': feature_name, 'VIF': vif_value})
    
    # Return as DataFrame sorted by VIF (highest first)
    vif_df = pd.DataFrame(vif_data)
    vif_df = vif_df.sort_values('VIF', ascending=False).reset_index(drop=True)
    
    return vif_df


def fit_quantile_regression(
    y: np.ndarray,
    X: np.ndarray,
    quantile: float = 0.5
) -> Any:
    """
    Fit quantile regression model for conditional quantile estimation.
    
    Quantile regression estimates conditional quantiles (e.g., median, 25th percentile)
    rather than conditional means. Useful for heterogeneous treatment effects
    and distributional analysis.
    
    Parameters
    ----------
    y : np.ndarray
        Dependent variable (1D array of shape (n_samples,)).
    X : np.ndarray
        Independent variables (2D array of shape (n_samples, n_features)).
        Constant term will be added automatically.
    quantile : float, default=0.5
        Quantile to fit, must be in (0, 1). Default is 0.5 for median regression.
        
    Returns
    -------
    QuantRegResults
        Fitted quantile regression results object from statsmodels.
    
    Raises
    ------
    ValueError
        If quantile is not in the interval (0, 1) or if input shapes are incompatible.
    
    Notes
    -----
    Uses statsmodels.regression.quantile_regression.QuantReg. Median regression
    (quantile=0.5) is robust to outliers in the dependent variable.
    """
    # Validate quantile parameter to ensure valid range
    if not 0 < quantile < 1:
        raise ValueError(f"Quantile must be in (0, 1), got {quantile}")
    
    # Validate input shapes
    if y.shape[0] != X.shape[0]:
        raise ValueError(
            f"Sample size mismatch: y has {y.shape[0]} samples, "
            f"X has {X.shape[0]} samples"
        )
    X_const = sm.add_constant(X)
    qr_model = QuantReg(y, X_const)
    qr_results = qr_model.fit(q=quantile)
    
    return qr_results
