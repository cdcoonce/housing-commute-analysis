"""RQ1: Housing-Commute Trade-Off Analysis.

Research Question:
How does average commute time influence housing affordability across metropolitan areas?

Methodology:
Uses ACS 5-year data estimates for median gross rent (B25064), median household
income (B19013), and commute data (B08303) to test the relationship between
commute times and rent burden. Controls for renter share, vehicle availability,
and population density to isolate the commute effect.

Model Specification:
    rent_to_income = beta_0 + beta_1(commute_min_proxy) + beta_2(commute_min_proxy^2) +
                     beta_3(renter_share) + beta_4(vehicle_access) + beta_5(pop_density) + e

Model Comparison:
    - Linear Model: rent_to_income ~ commute + renter_share + vehicle_access + pop_density
    - Quadratic Model: rent_to_income ~ commute + commute^2 + renter_share + vehicle_access + pop_density
    - Selection Criteria: Akaike Information Criterion (AIC) - lower is better

Validation:
    - 3-fold cross-validation RMSE for predictive accuracy
    - Adjusted R-squared for explanatory power
    - Variance Inflation Factor (VIF) to check for multicollinearity (VIF > 10 problematic)
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import polars as pl
import statsmodels.api as sm

from .data_loader import METRO_NAMES
from .models import calculate_vif, cv_rmse, fit_ols_robust
from .reporting import save_markdown_table
from .results import RQ1Results
from .visualization import plot_diagnostics

logger = logging.getLogger(__name__)


def analyze_rq1(df: pl.DataFrame) -> RQ1Results:
    """Perform RQ1 statistical analysis without any I/O.

    Fits linear and quadratic OLS models with robust standard errors,
    selects the best model via AIC, and computes cross-validation RMSE
    and VIF diagnostics.

    Parameters
    ----------
    df : pl.DataFrame
        Input DataFrame with ZCTA-level data containing:
        rent_to_income, commute_min_proxy, renter_share, vehicle_access,
        pop_density, and ZCTA5CE columns.

    Returns
    -------
    RQ1Results
        Typed container with all analysis outputs.

    Raises
    ------
    ValueError
        If required columns are missing from the input DataFrame.
    """
    logger.info("=" * 60)
    logger.info("RQ1: Housing-Commute Trade-Off Analysis")
    logger.info("=" * 60)

    # Step 1: Validate and prepare data
    required_cols = ['rent_to_income', 'commute_min_proxy', 'renter_share',
                     'vehicle_access', 'pop_density']
    missing_cols = [col for col in required_cols if col not in df.columns]

    if missing_cols:
        raise ValueError(f"Missing required columns for RQ1 analysis: {missing_cols}")

    df_clean = df.select(required_cols + ['ZCTA5CE']).drop_nulls()
    n_dropped = len(df) - len(df_clean)

    if n_dropped > 0:
        logger.info(f"Dropped {n_dropped} ZCTAs with missing values")
    logger.info(f"Analysis sample: {len(df_clean)} ZCTAs")

    # Extract arrays
    rent_to_income = df_clean['rent_to_income'].to_numpy()
    commute_time_min = df_clean['commute_min_proxy'].to_numpy()
    renter_share_pct = df_clean['renter_share'].to_numpy()
    vehicle_access_pct = df_clean['vehicle_access'].to_numpy()
    pop_density_per_km2 = df_clean['pop_density'].to_numpy()

    # Step 2: Build feature matrices
    feature_matrix_linear = np.column_stack([
        commute_time_min, renter_share_pct, vehicle_access_pct, pop_density_per_km2
    ])
    feature_names_linear = ['commute_min_proxy', 'renter_share', 'vehicle_access', 'pop_density']

    commute_squared = commute_time_min ** 2
    feature_matrix_quad = np.column_stack([
        commute_time_min, commute_squared, renter_share_pct,
        vehicle_access_pct, pop_density_per_km2
    ])
    feature_names_quad = ['commute_min_proxy', 'commute_min_proxy²', 'renter_share',
                          'vehicle_access', 'pop_density']

    # Step 3: VIF
    logger.info("Checking for multicollinearity (VIF)...")
    vif_linear = calculate_vif(feature_matrix_linear, feature_names_linear)
    vif_quad = calculate_vif(feature_matrix_quad, feature_names_quad)

    # Step 4: Fit models
    logger.info("Fitting linear model...")
    model_linear = fit_ols_robust(rent_to_income, feature_matrix_linear, feature_names_linear)
    cv_rmse_linear_val, _ = cv_rmse(feature_matrix_linear, rent_to_income, k=3)

    logger.info(f"Linear: Adj R²={model_linear['adj_r2']:.4f}, AIC={model_linear['aic']:.2f}")

    logger.info("Fitting quadratic model...")
    model_quad = fit_ols_robust(rent_to_income, feature_matrix_quad, feature_names_quad)
    cv_rmse_quad_val, _ = cv_rmse(feature_matrix_quad, rent_to_income, k=3)

    logger.info(f"Quadratic: Adj R²={model_quad['adj_r2']:.4f}, AIC={model_quad['aic']:.2f}")

    # Step 5: Model selection via AIC
    if model_linear['aic'] < model_quad['aic']:
        best_model = model_linear
        best_model_name = 'Linear'
        best_feature_matrix = feature_matrix_linear
        best_features = feature_names_linear
    else:
        best_model = model_quad
        best_model_name = 'Quadratic'
        best_feature_matrix = feature_matrix_quad
        best_features = feature_names_quad

    logger.info(f"Selected: {best_model_name} (AIC={best_model['aic']:.2f})")

    # Step 6: Predictions and residuals
    feature_matrix_with_const = sm.add_constant(best_feature_matrix)
    y_pred = best_model['results'].predict(feature_matrix_with_const)
    resid = best_model['results'].resid

    # Build model DataFrame
    model_df = df_clean.select(['ZCTA5CE', 'rent_to_income', 'commute_min_proxy',
                                 'renter_share', 'vehicle_access', 'pop_density'])
    model_df = model_df.with_columns([
        pl.Series('predicted', y_pred),
        pl.Series('residuals', resid)
    ])

    return RQ1Results(
        model_linear=model_linear,
        model_quad=model_quad,
        best_model_name=best_model_name,
        best_model=best_model,
        cv_rmse_linear=cv_rmse_linear_val,
        cv_rmse_quad=cv_rmse_quad_val,
        vif_linear=vif_linear,
        vif_quad=vif_quad,
        y_pred=y_pred,
        residuals=resid,
        y_true=rent_to_income,
        commute_time=commute_time_min,
        feature_matrix=best_feature_matrix,
        feature_names=best_features,
        sample_size=len(df_clean),
        model_df=model_df,
    )


def report_rq1(
    results: RQ1Results,
    out_dir: Path,
    fig_dir: Path,
    metro: str,
) -> None:
    """Write RQ1 results to markdown and generate diagnostic plots.

    Parameters
    ----------
    results : RQ1Results
        Output from analyze_rq1().
    out_dir : Path
        Markdown output directory.
    fig_dir : Path
        Figure output directory.
    metro : str
        Metro code for file naming.
    """
    best_model = results.best_model
    best_model_name = results.best_model_name
    best_features = results.feature_names
    best_cv_rmse = (results.cv_rmse_linear if best_model_name == 'Linear'
                    else results.cv_rmse_quad)
    best_vif = results.vif_linear if best_model_name == 'Linear' else results.vif_quad

    # Diagnostic plots
    plot_diagnostics(
        y_true=results.y_true,
        y_pred=results.y_pred,
        resid=results.residuals,
        x_var=results.commute_time,
        x_label='Commute Time (minutes)',
        out_dir=fig_dir,
        prefix=f"rq1_{metro.lower()}",
        model_results=best_model['results'],
        X_matrix=results.feature_matrix,
    )

    # Markdown report
    md_path = out_dir / f"analysis_summary_{metro.lower()}.md"

    with open(md_path, 'w') as f:
        f.write(f"# RQ1 Analysis: {METRO_NAMES[metro]}\n\n")
        f.write("## Research Question\n\n")
        f.write("How does average commute time influence housing affordability across metropolitan areas?\n\n")
        f.write("## Methodology\n\n")
        f.write("**Data Sources:**\n\n")
        f.write("- Median Gross Rent: ACS Table B25064\n")
        f.write("- Median Household Income: ACS Table B19013\n")
        f.write("- Commute Time to Work: ACS Table B08303\n")
        f.write("- Housing Tenure: ACS Table B25003\n")
        f.write("- Vehicle Availability: ACS Table B08201\n")
        f.write("- Zillow Observed Rent Index (ZORI)\n")
        f.write("- OpenStreetMap Transit Data\n\n")
        f.write("**Model Specification:**\n\n")
        f.write("```text\n")
        f.write("rent_to_income = B0 + B1(commute_min_proxy) + B2(commute_min_proxy^2) +\n")
        f.write("                 B3(renter_share) + B4(vehicle_access) + B5(pop_density) + e\n")
        f.write("```\n\n")
        f.write("**Analysis:**\n\n")
        f.write("- Metro-specific linear regression with non-linearity testing\n")
        f.write("- Model comparison: Linear vs Quadratic specification\n")
        f.write("- Model selection: Akaike Information Criterion (AIC)\n")
        f.write("- Validation: 3-fold cross-validation RMSE\n")
        f.write("- Multicollinearity check: Variance Inflation Factor (VIF)\n\n")
        f.write(f"**Sample Size:** {results.sample_size} ZCTAs\n\n")
        f.write("---\n\n")

    # Model comparison table
    comparison_data = {
        'Model': ['Linear', 'Quadratic'],
        'Adj R²': [f"{results.model_linear['adj_r2']:.4f}",
                    f"{results.model_quad['adj_r2']:.4f}"],
        'AIC': [f"{results.model_linear['aic']:.2f}",
                f"{results.model_quad['aic']:.2f}"],
        'CV-RMSE': [f"{results.cv_rmse_linear:.4f}",
                     f"{results.cv_rmse_quad:.4f}"],
        'Selected': ['X' if best_model_name == 'Linear' else '',
                     'X' if best_model_name == 'Quadratic' else ''],
    }
    save_markdown_table(comparison_data, md_path, "Model Comparison")

    # Coefficients table
    coef_data = {
        'Variable': ['Intercept'] + best_features,
        'Coefficient': [f"{val:.4f}" for val in best_model['params']],
        'Std Error': [f"{val:.4f}" for val in best_model['std_errors']],
        'p-value': [f"{val:.4f}" if val >= 0.0001 else '<0.0001'
                    for val in best_model['pvalues']],
        'Sig': ['***' if v < 0.001 else '**' if v < 0.01 else '*' if v < 0.05 else ''
                for v in best_model['pvalues']],
    }
    save_markdown_table(coef_data, md_path, f"{best_model_name} Model Coefficients")

    # VIF table
    vif_data = {
        'Variable': best_vif['Feature'].tolist(),
        'VIF': [f"{val:.2f}" for val in best_vif['VIF'].tolist()],
        'Interpretation': [
            'Severe (>10)' if val > 10 else 'High (5-10)' if val > 5
            else 'Moderate (1-5)' if val > 1 else 'None (=1)'
            for val in best_vif['VIF'].tolist()
        ],
    }
    save_markdown_table(vif_data, md_path, "Multicollinearity Diagnostics (VIF)")

    # Interpretation
    with open(md_path, 'a') as f:
        f.write("## Interpretation\n\n")
        f.write(f"The **{best_model_name.lower()} model** was selected based on "
                "Akaike Information Criterion (AIC). ")

        if best_model_name == 'Quadratic':
            commute_sq_coef = best_model['params'][2]
            f.write(f"The quadratic term (B2 = {commute_sq_coef:.4f}) suggests a ")
            if commute_sq_coef > 0:
                f.write("**convex relationship**: rent burden increases more rapidly "
                        "at longer commute times. ")
            else:
                f.write("**concave relationship**: rent burden increases less rapidly "
                        "at longer commute times. ")
        else:
            commute_coef = best_model['params'][1]
            f.write(f"The linear relationship (B1 = {commute_coef:.4f}) indicates that ")
            if commute_coef > 0:
                f.write("**longer commutes are associated with higher rent burden**. ")
            else:
                f.write("**longer commutes are associated with lower rent burden** "
                        "(housing-commute trade-off). ")

        f.write(f"The model explains **{best_model['adj_r2']*100:.1f}%** of the variance "
                f"in rent-to-income ratios (Adj R² = {best_model['adj_r2']:.4f}).\n\n")

        commute_pval = best_model['pvalues'][1]
        if commute_pval < 0.001:
            f.write("Commute time has a **highly significant** relationship with "
                    "rent burden (p < 0.001).\n\n")
        elif commute_pval < 0.01:
            f.write("Commute time has a **very significant** relationship with "
                    "rent burden (p < 0.01).\n\n")
        elif commute_pval < 0.05:
            f.write("Commute time has a **statistically significant** relationship "
                    "with rent burden (p < 0.05).\n\n")
        else:
            f.write(f"Commute time does **not** show a statistically significant "
                    f"relationship with rent burden (p = {commute_pval:.4f}).\n\n")

        f.write(f"**Cross-Validation:** 3-fold CV-RMSE = {best_cv_rmse:.4f}, indicating ")
        if best_cv_rmse < 0.10:
            f.write("excellent out-of-sample predictive accuracy.\n\n")
        elif best_cv_rmse < 0.15:
            f.write("good out-of-sample predictive accuracy.\n\n")
        else:
            f.write("moderate out-of-sample predictive accuracy.\n\n")

        max_vif = best_vif['VIF'].max()
        if max_vif > 10:
            f.write(f"**Multicollinearity Warning:** Maximum VIF = {max_vif:.2f} > 10. "
                    "Coefficient estimates may be unstable.\n\n")
        elif max_vif > 5:
            f.write(f"**Moderate Multicollinearity:** Maximum VIF = {max_vif:.2f} "
                    "(5-10 range). Monitor coefficient stability.\n\n")
        else:
            f.write(f"**No Multicollinearity Issues:** Maximum VIF = {max_vif:.2f} < 5. "
                    "Coefficient estimates are stable.\n\n")

        f.write("**Control Variables:**\n")
        for i, feature in enumerate(best_features):
            if feature not in ['commute_min_proxy', 'commute_min_proxy²']:
                coef_val = best_model['params'][i + 1]
                pval = best_model['pvalues'][i + 1]
                sig = ('***' if pval < 0.001 else '**' if pval < 0.01
                       else '*' if pval < 0.05 else 'ns')
                f.write(f"- **{feature}**: B = {coef_val:.4f} ({sig})\n")

        f.write("\n**Diagnostic Plots:**\n")
        f.write(f"- `rq1_{metro.lower()}_scatter.png`: Scatter plot\n")
        f.write(f"- `rq1_{metro.lower()}_residuals.png`: Residuals vs fitted\n")
        f.write(f"- `rq1_{metro.lower()}_qq.png`: Q-Q plot\n")
        f.write(f"- `rq1_{metro.lower()}_hist.png`: Histogram of residuals\n\n")
        f.write("---\n")

    # Save model data CSV
    results.model_df.write_csv(out_dir / f"rq1_model_data_{metro.lower()}.csv")

    logger.info(f"RQ1 results saved to {md_path}")


def run_rq1(df: pl.DataFrame, out_dir: Path, fig_dir: Path, metro: str) -> None:
    """RQ1: Housing-commute trade-off analysis (full pipeline).

    Delegates to analyze_rq1() and report_rq1() for separation of concerns.

    Parameters
    ----------
    df : pl.DataFrame
        Input DataFrame with ZCTA-level data.
    out_dir : Path
        Output directory for results.
    fig_dir : Path
        Figure output directory.
    metro : str
        Metro code for labeling outputs.
    """
    results = analyze_rq1(df)
    report_rq1(results, out_dir, fig_dir, metro)
