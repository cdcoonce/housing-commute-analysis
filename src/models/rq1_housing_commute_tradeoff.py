"""
RQ1: Housing-Commute Trade-Off Analysis

Research Question:
How does average commute time influence housing affordability across metropolitan areas?

Methodology:
Uses ACS 5-year data estimates for median gross rent (B25064), median household
income (B19013), and commute data (B08303) to test the relationship between
commute times and rent burden. Controls for renter share, vehicle availability,
and population density to isolate the commute effect.

Model Specification:
    rent_to_income = β₀ + β₁(commute_min_proxy) + β₂(commute_min_proxy²) +
                     β₃(renter_share) + β₄(vehicle_access) + β₅(pop_density) + ε

Model Comparison:
    - Linear Model: rent_to_income ~ commute + renter_share + vehicle_access + pop_density
    - Quadratic Model: rent_to_income ~ commute + commute² + renter_share + vehicle_access + pop_density
    - Selection Criteria: Akaike Information Criterion (AIC) - lower is better

Validation:
    - 3-fold cross-validation RMSE for predictive accuracy
    - Adjusted R² for explanatory power
    - Variance Inflation Factor (VIF) to check for multicollinearity (VIF > 10 problematic)

Author: DAT490 Team
Date: November 2025
"""

import logging
from pathlib import Path

import numpy as np
import polars as pl
import statsmodels.api as sm

from .data_loader import METRO_NAMES
from .models import calculate_vif, cv_rmse, fit_ols_robust
from .reporting import save_markdown_table
from .visualization import plot_diagnostics

logger = logging.getLogger(__name__)


def run_rq1(df: pl.DataFrame, out_dir: Path, fig_dir: Path, metro: str) -> None:
    """
    RQ1: Housing-commute trade-off OLS analysis.
    
    Tests whether renters in affordable areas face longer commutes by comparing
    linear vs quadratic model specifications. Uses the exact methodology specified
    in the research proposal.
    
    Parameters
    ----------
    df : pl.DataFrame
        Input DataFrame with ZCTA-level data containing:
        - rent_to_income: Dependent variable (rent as fraction of monthly income)
        - commute_min_proxy: Primary predictor (average commute time in minutes)
        - renter_share: Control variable (% of units that are renter-occupied)
        - vehicle_access: Control variable (% of households with 1+ vehicles)
        - pop_density: Control variable (people per km²)
    out_dir : Path
        Output directory for results (markdown tables, CSV files).
    fig_dir : Path
        Figure output directory for diagnostic plots.
    metro : str
        Metro code (PHX, LA, DFW, MEM) for labeling outputs.
    
    Returns
    -------
    None
        Saves results to files in out_dir and fig_dir.
    
    Notes
    -----
    Model Selection:
    - Compares linear vs quadratic specifications using AIC
    - Lower AIC indicates better model fit penalized for complexity
    
    Validation:
    - 3-fold cross-validation RMSE for out-of-sample performance
    - VIF calculation to detect multicollinearity (VIF > 10 problematic)
    - Adjusted R² to assess variance explained
    
    Outputs:
    - analysis_summary_{metro}.md: Model comparison and coefficients
    - rq1_model_data_{metro}.csv: Data with predictions and residuals
    - Four diagnostic plots: scatter, residuals, Q-Q, histogram
    """
    logger.info("=" * 60)
    logger.info("RQ1: Housing-Commute Trade-Off Analysis")
    logger.info("=" * 60)
    logger.info("Methodology: Metro-specific linear regression with non-linearity testing")
    logger.info("Equation: rent_to_income = β₀ + β₁(commute) + β₂(commute²) + β₃(renter_share) + β₄(vehicle_access) + β₅(pop_density) + ε")

    
    # ==================================================================================
    # STEP 1: Prepare data and check for required control variables
    # ==================================================================================
    required_cols = ['rent_to_income', 'commute_min_proxy', 'renter_share', 'vehicle_access', 'pop_density']
    missing_cols = [col for col in required_cols if col not in df.columns]
    
    if missing_cols:
        logger.error(f"Missing required columns: {missing_cols}")
        logger.error("Please ensure the pipeline includes B25003 (tenure), B08201 (vehicles), and pop_density calculation")
        raise ValueError(f"Missing required columns for RQ1 analysis: {missing_cols}")
    
    # Select complete cases (drop rows with missing values in any required column)
    df_clean = df.select(required_cols + ['ZCTA5CE']).drop_nulls()
    n_dropped = len(df) - len(df_clean)
    
    if n_dropped > 0:
        logger.info(f"Dropped {n_dropped} ZCTAs with missing values in required columns")
    
    logger.info(f"Analysis sample: {len(df_clean)} ZCTAs")
    
    # Extract dependent variable
    y = df_clean['rent_to_income'].to_numpy()
    
    # ==================================================================================
    # STEP 2: Prepare feature matrices for linear and quadratic models
    # ==================================================================================
    # Primary predictor: commute time (minutes)
    commute = df_clean['commute_min_proxy'].to_numpy()
    
    # Control variables
    renter_share = df_clean['renter_share'].to_numpy()
    vehicle_access = df_clean['vehicle_access'].to_numpy()
    pop_density = df_clean['pop_density'].to_numpy()
    
    # Model 1: Linear specification
    # rent_to_income = β₀ + β₁(commute) + β₂(renter_share) + β₃(vehicle_access) + β₄(pop_density) + ε
    X_linear = np.column_stack([commute, renter_share, vehicle_access, pop_density])
    feature_names_linear = ['commute_min_proxy', 'renter_share', 'vehicle_access', 'pop_density']
    
    # Model 2: Quadratic specification
    # rent_to_income = β₀ + β₁(commute) + β₂(commute²) + β₃(renter_share) + β₄(vehicle_access) + β₅(pop_density) + ε
    commute_squared = commute ** 2
    X_quad = np.column_stack([commute, commute_squared, renter_share, vehicle_access, pop_density])
    feature_names_quad = ['commute_min_proxy', 'commute_min_proxy²', 'renter_share', 'vehicle_access', 'pop_density']

    
    # ==================================================================================
    # STEP 3: Check for multicollinearity using VIF
    # ==================================================================================
    logger.info("Checking for multicollinearity (VIF)...")
    
    vif_linear = calculate_vif(X_linear, feature_names_linear)
    logger.info("VIF for linear model:")
    for _, row in vif_linear.iterrows():
        vif_warning = "HIGH" if row['VIF'] > 10 else "OK" if row['VIF'] < 5 else "MODERATE"
        logger.info(f"  {row['Feature']}: {row['VIF']:.2f}{vif_warning}")
    
    vif_quad = calculate_vif(X_quad, feature_names_quad)
    logger.info("VIF for quadratic model:")
    for _, row in vif_quad.iterrows():
        vif_warning = "HIGH" if row['VIF'] > 10 else "OK" if row['VIF'] < 5 else "MODERATE"
        logger.info(f"  {row['Feature']}: {row['VIF']:.2f}{vif_warning}")
    
    # ==================================================================================
    # STEP 4: Fit linear model
    # ==================================================================================
    logger.info("Fitting linear model...")
    model_linear = fit_ols_robust(y, X_linear, feature_names_linear)
    
    # 3-fold cross-validation for linear model
    cv_rmse_linear, cv_folds_linear = cv_rmse(X_linear, y, k=3)
    
    logger.info(f"Linear Model Results:")
    logger.info(f"  Adj R²: {model_linear['adj_r2']:.4f}")
    logger.info(f"  AIC: {model_linear['aic']:.2f}")
    logger.info(f"  CV-RMSE (3-fold): {cv_rmse_linear:.4f} (folds: {[f'{x:.4f}' for x in cv_folds_linear]})")
    
    # ==================================================================================
    # STEP 5: Fit quadratic model
    # ==================================================================================
    logger.info("Fitting quadratic model...")
    model_quad = fit_ols_robust(y, X_quad, feature_names_quad)
    
    # 3-fold cross-validation for quadratic model
    cv_rmse_quad, cv_folds_quad = cv_rmse(X_quad, y, k=3)
    
    logger.info(f"Quadratic Model Results:")
    logger.info(f"  Adj R²: {model_quad['adj_r2']:.4f}")
    logger.info(f"  AIC: {model_quad['aic']:.2f}")
    logger.info(f"  CV-RMSE (3-fold): {cv_rmse_quad:.4f} (folds: {[f'{x:.4f}' for x in cv_folds_quad]})")
    
    # ==================================================================================
    # STEP 6: Model selection via AIC (lower is better)
    # ==================================================================================
    if model_linear['aic'] < model_quad['aic']:
        best_model = model_linear
        best_model_name = 'Linear'
        best_X = X_linear
        best_features = feature_names_linear
        best_cv_rmse = cv_rmse_linear
        best_vif = vif_linear
    else:
        best_model = model_quad
        best_model_name = 'Quadratic'
        best_X = X_quad
        best_features = feature_names_quad
        best_cv_rmse = cv_rmse_quad
        best_vif = vif_quad
    
    aic_diff = abs(model_linear['aic'] - model_quad['aic'])
    logger.info(f"{'='*60}")
    logger.info(f"Model Selection: {best_model_name} model selected (AIC = {best_model['aic']:.2f})")
    logger.info(f"  AIC difference: {aic_diff:.2f} (lower AIC is better)")
    logger.info(f"  Rule of thumb: ΔAIC > 2 indicates substantial evidence for better model")
    logger.info(f"{'='*60}\n")
    
    # ==================================================================================
    # STEP 7: Generate predictions and residuals for diagnostics
    # ==================================================================================
    X_const = sm.add_constant(best_X)
    y_pred = best_model['results'].predict(X_const)
    resid = best_model['results'].resid
    
    # ==================================================================================
    # STEP 8: Create diagnostic plots
    # ==================================================================================
    plot_diagnostics(
        y_true=y,
        y_pred=y_pred,
        resid=resid,
        x_var=commute,  # Always plot against commute time for interpretability
        x_label='Commute Time (minutes)',
        out_dir=fig_dir,
        prefix=f"rq1_{metro.lower()}",
        model_results=best_model['results'],  # Pass model for smooth curve generation
        X_matrix=best_X  # Pass feature matrix for grid predictions
    )
    
    # Save results to markdown with metro-specific filename
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
        f.write("rent_to_income = β₀ + β₁(commute_min_proxy) + β₂(commute_min_proxy²) +\n")
        f.write("                 β₃(renter_share) + β₄(vehicle_access) + β₅(pop_density) + ε\n")
        f.write("```\n\n")
        f.write("**Analysis:**\n\n")
        f.write("- Metro-specific linear regression with non-linearity testing\n")
        f.write("- Model comparison: Linear vs Quadratic specification\n")
        f.write("- Model selection: Akaike Information Criterion (AIC)\n")
        f.write("- Validation: 3-fold cross-validation RMSE\n")
        f.write("- Multicollinearity check: Variance Inflation Factor (VIF)\n\n")
        f.write(f"**Sample Size:** {len(df_clean)} ZCTAs\n\n")
        f.write("---\n\n")
    
    # ==================================================================================
    # STEP 9: Save results to markdown report
    # ==================================================================================
    # Model comparison table
    comparison_data = {
        'Model': ['Linear', 'Quadratic'],
        'Adj R²': [f"{model_linear['adj_r2']:.4f}", f"{model_quad['adj_r2']:.4f}"],
        'AIC': [f"{model_linear['aic']:.2f}", f"{model_quad['aic']:.2f}"],
        'CV-RMSE': [f"{cv_rmse_linear:.4f}", f"{cv_rmse_quad:.4f}"],
        'Selected': ['X' if best_model_name == 'Linear' else '', 'X' if best_model_name == 'Quadratic' else '']
    }
    save_markdown_table(comparison_data, md_path, "Model Comparison")
    
    # Best model coefficients with significance stars
    coef_data = {
        'Variable': ['Intercept'] + best_features,
        'Coefficient': [f"{best_model['params'][0]:.4f}"] + [f"{val:.4f}" for val in best_model['params'][1:]],
        'Std Error': [f"{best_model['std_errors'][0]:.4f}"] + [f"{val:.4f}" for val in best_model['std_errors'][1:]],
        'p-value': [f"{best_model['pvalues'][0]:.4f}" if best_model['pvalues'][0] >= 0.0001 else '<0.0001'] +
                   [f"{val:.4f}" if val >= 0.0001 else '<0.0001' for val in best_model['pvalues'][1:]],
        'Sig': ['***' if best_model['pvalues'][0] < 0.001 else '**' if best_model['pvalues'][0] < 0.01 else '*' if best_model['pvalues'][0] < 0.05 else ''] +
               ['***' if val < 0.001 else '**' if val < 0.01 else '*' if val < 0.05 else '' for val in best_model['pvalues'][1:]]
    }
    save_markdown_table(coef_data, md_path, f"{best_model_name} Model Coefficients")
    
    # Variance Inflation Factor (multicollinearity check)
    vif_data = {
        'Variable': best_vif['Feature'].tolist(),
        'VIF': [f"{val:.2f}" for val in best_vif['VIF'].tolist()],
        'Interpretation': [
            'Severe (>10)' if val > 10 else 'High (5-10)' if val > 5 else 'Moderate (1-5)' if val > 1 else 'None (=1)'
            for val in best_vif['VIF'].tolist()
        ]
    }
    save_markdown_table(vif_data, md_path, "Multicollinearity Diagnostics (VIF)")
    
    # Interpretation section
    with open(md_path, 'a') as f:
        f.write("## Interpretation\n\n")
        f.write(f"The **{best_model_name.lower()} model** was selected based on Akaike Information Criterion (AIC). ")
        
        if best_model_name == 'Quadratic':
            commute_coef = best_model['params'][1]
            commute_sq_coef = best_model['params'][2]
            f.write(f"The quadratic term (β₂ = {commute_sq_coef:.4f}) suggests a ")
            if commute_sq_coef > 0:
                f.write("**convex relationship**: rent burden increases more rapidly at longer commute times. ")
            else:
                f.write("**concave relationship**: rent burden increases less rapidly at longer commute times. ")
        else:
            commute_coef = best_model['params'][1]
            f.write(f"The linear relationship (β₁ = {commute_coef:.4f}) indicates that ")
            if commute_coef > 0:
                f.write("**longer commutes are associated with higher rent burden**. ")
            else:
                f.write("**longer commutes are associated with lower rent burden** (housing-commute trade-off). ")
        
        f.write(f"The model explains **{best_model['adj_r2']*100:.1f}%** of the variance in rent-to-income ratios ")
        f.write(f"(Adj R² = {best_model['adj_r2']:.4f}).\n\n")
        
        # Statistical significance of commute coefficient
        commute_pval = best_model['pvalues'][1]
        if commute_pval < 0.001:
            f.write(f"Commute time has a **highly significant** relationship with rent burden (p < 0.001).\n\n")
        elif commute_pval < 0.01:
            f.write(f"Commute time has a **very significant** relationship with rent burden (p < 0.01).\n\n")
        elif commute_pval < 0.05:
            f.write(f"Commute time has a **statistically significant** relationship with rent burden (p < 0.05).\n\n")
        else:
            f.write(f"Commute time does **not** show a statistically significant relationship with rent burden (p = {commute_pval:.4f}).\n\n")
        
        # Cross-validation and model fit
        f.write(f"**Cross-Validation:** 3-fold CV-RMSE = {best_cv_rmse:.4f}, indicating ")
        if best_cv_rmse < 0.10:
            f.write("excellent out-of-sample predictive accuracy.\n\n")
        elif best_cv_rmse < 0.15:
            f.write("good out-of-sample predictive accuracy.\n\n")
        else:
            f.write("moderate out-of-sample predictive accuracy.\n\n")
        
        # Multicollinearity assessment
        max_vif = best_vif['VIF'].max()
        if max_vif > 10:
            f.write(f"**Multicollinearity Warning:** Maximum VIF = {max_vif:.2f} > 10. ")
            f.write("Coefficient estimates may be unstable. Consider removing or combining highly correlated predictors.\n\n")
        elif max_vif > 5:
            f.write(f"**Moderate Multicollinearity:** Maximum VIF = {max_vif:.2f} (5-10 range). ")
            f.write("Monitor coefficient stability but generally acceptable.\n\n")
        else:
            f.write(f"**No Multicollinearity Issues:** Maximum VIF = {max_vif:.2f} < 5. ")
            f.write("Coefficient estimates are stable.\n\n")
        
        # Control variable interpretation
        f.write("**Control Variables:**\n")
        for i, feature in enumerate(best_features):
            if feature not in ['commute_min_proxy', 'commute_min_proxy²']:
                coef_val = best_model['params'][i + 1]  # +1 for constant
                pval = best_model['pvalues'][i + 1]
                sig = '***' if pval < 0.001 else '**' if pval < 0.01 else '*' if pval < 0.05 else 'ns'
                f.write(f"- **{feature}**: β = {coef_val:.4f} ({sig})\n")
        
        f.write("\n**Diagnostic Plots:**\n")
        f.write(f"- `rq1_{metro.lower()}_scatter.png`: Scatter plot of commute time vs rent-to-income ratio\n")
        f.write(f"- `rq1_{metro.lower()}_residuals.png`: Residuals vs fitted values (check for heteroscedasticity)\n")
        f.write(f"- `rq1_{metro.lower()}_qq.png`: Q-Q plot (check for normality of residuals)\n")
        f.write(f"- `rq1_{metro.lower()}_hist.png`: Histogram of residuals (check for distribution)\n\n")
        f.write("---\n")
    
    # ==================================================================================
    # STEP 10: Save model data with predictions and residuals
    # ==================================================================================
    model_df = df_clean.select(['ZCTA5CE', 'rent_to_income', 'commute_min_proxy', 
                                 'renter_share', 'vehicle_access', 'pop_density'])
    model_df = model_df.with_columns([
        pl.Series('predicted', y_pred),
        pl.Series('residuals', resid)
    ])
    model_df.write_csv(out_dir / f"rq1_model_data_{metro.lower()}.csv")
    
    logger.info(f"\n{'='*60}")
    logger.info("RQ1 analysis complete")
    logger.info(f"  Results saved to: {md_path}")
    logger.info(f"  Model data saved to: rq1_model_data_{metro.lower()}.csv")
    logger.info(f"  Diagnostic plots saved to: {fig_dir}")
    logger.info(f"{'='*60}\n")
