"""
RQ3: Combined Affordability-Commute Index (ACI) Analysis

This module computes the Affordability-Commute Index (ACI) as the sum of
standardized rent burden and commute time, performs OLS and quantile regression
modeling, and generates visualizations including optional choropleth maps.

Author: DAT490 Team
Date: November 2025
"""

import logging
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import statsmodels.api as sm
from statsmodels.regression.quantile_regression import QuantReg

from .data_loader import METRO_NAMES
from .models import cv_rmse, fit_ols_robust
from .preprocessing import compute_majority_race
from .reporting import save_markdown_table

logger = logging.getLogger(__name__)


def run_rq3(df: pl.DataFrame, out_dir: Path, fig_dir: Path, metro: str, zcta_shp: Optional[Path] = None) -> None:
    """
    RQ3: Combined pressure analysis (ACI).
    
    Computes Affordability-Commute Index as the sum of standardized rent burden
    and commute time. Models ACI using OLS and quantile regression, generates
    visualizations including optional choropleth map.
    
    Args:
        df: Input DataFrame with ZCTA-level data
        out_dir: Output directory for results
        fig_dir: Figure output directory
        metro: Metro code (PHX, LA, DFW, MEM)
        zcta_shp: Optional path to ZCTA shapefile for mapping
    """
    logger.info("=" * 60)
    logger.info("RQ3: Combined Affordability-Commute Index (ACI)")
    logger.info("=" * 60)
    
    # Compute ACI
    logger.info("Computing ACI = z(rent_to_income) + z(commute_min_proxy)")
    
    rent_mean = df['rent_to_income'].mean()
    rent_std = df['rent_to_income'].std()
    commute_mean = df['commute_min_proxy'].mean()
    commute_std = df['commute_min_proxy'].std()
    
    df = df.with_columns([
        ((pl.col('rent_to_income') - rent_mean) / rent_std).alias('rent_z'),
        ((pl.col('commute_min_proxy') - commute_mean) / commute_std).alias('commute_z')
    ])
    
    df = df.with_columns(
        (pl.col('rent_z') + pl.col('commute_z')).alias('ACI')
    )
    
    logger.info(f"ACI computed. Mean: {df['ACI'].mean():.3f}, Std: {df['ACI'].std():.3f}")
    
    # Classify ZCTAs into ACI tiers (Low/Medium/High terciles)
    logger.info("Classifying ZCTAs into ACI tiers...")
    
    aci_q33 = df['ACI'].quantile(0.333)
    aci_q67 = df['ACI'].quantile(0.667)
    
    df = df.with_columns(
        pl.when(pl.col('ACI') <= aci_q33).then(pl.lit('Low'))
        .when(pl.col('ACI') <= aci_q67).then(pl.lit('Medium'))
        .otherwise(pl.lit('High'))
        .alias('ACI_tier')
    )
    
    logger.info(f"ACI tier boundaries: Low ≤ {aci_q33:.3f}, Medium ≤ {aci_q67:.3f}, High > {aci_q67:.3f}")
    
    # Log tier distribution
    tier_summary = df.group_by('ACI_tier').agg([
        pl.count().alias('n_zctas'),
        pl.col('ACI').mean().alias('mean_aci'),
        pl.col('ACI').min().alias('min_aci'),
        pl.col('ACI').max().alias('max_aci')
    ]).sort('ACI_tier')
    
    logger.info(f"ACI tier distribution:\n{tier_summary}")
    
    # Compute majority race if not already present (using shared function)
    if 'majority_race' not in df.columns:
        df = compute_majority_race(df)
    
    # OLS: ACI ~ stops_per_km2 + zori + controls
    # ACI is combined pressure, so we model it with transit access, housing costs, and demographics
    df_model = df.filter(pl.col('ACI').is_not_null())
    
    feature_candidates = []
    
    # Primary predictors: transit density and housing costs
    if 'stops_per_km2' in df_model.columns:
        feature_candidates.append('stops_per_km2')
    
    if 'zori' in df_model.columns:
        feature_candidates.append('zori')
    
    # Controls for RQ3: income, transportation mode, population density
    # These capture structural factors affecting combined housing-commute burden
    for col in ['median_income', 'pct_transit', 'pct_drive_alone', 'total_pop']:
        if col in df_model.columns:
            feature_candidates.append(col)
    
    if feature_candidates:
        filter_expr = pl.col('ACI').is_not_null()
        for feat in feature_candidates:
            filter_expr = filter_expr & pl.col(feat).is_not_null()
        
        df_model = df_model.filter(filter_expr)
        
        logger.info(f"After filtering for complete cases: {df_model.shape[0]} observations")
        
        if df_model.shape[0] < 10:
            logger.warning(f"Too few complete cases ({df_model.shape[0]}) for ACI model, skipping OLS")
            aci_model = None
            X_list = []
            feature_names = []
        else:
            y_aci = df_model['ACI'].to_numpy()
            X_list = []
            feature_names = []
            
            for feat in feature_candidates:
                X_col = df_model[feat].to_numpy()
                if not np.any(np.isnan(X_col)) and not np.any(np.isinf(X_col)):
                    X_list.append(X_col)
                    feature_names.append(feat)
                else:
                    logger.warning(f"Feature {feat} still contains NaN/inf after filtering, skipping")
            
            if not X_list:
                logger.warning("No valid predictors after filtering, skipping OLS")
                aci_model = None
            else:
                X_aci = np.column_stack(X_list)
                
                logger.info(f"Fitting OLS for ACI with features: {feature_names}")
                aci_model = fit_ols_robust(y_aci, X_aci, feature_names)
                cv_rmse_aci, _ = cv_rmse(X_aci, y_aci, k=5)
                
                logger.info(f"ACI OLS - Adj R²: {aci_model['adj_r2']:.4f}, AIC: {aci_model['aic']:.2f}, CV-RMSE: {cv_rmse_aci:.4f}")
    else:
        logger.warning("No predictors available for ACI model, skipping OLS")
        aci_model = None
        X_list = []
        feature_names = []
        df_model = df.filter(pl.col('ACI').is_not_null())
    
    # Quantile regression
    logger.info("Fitting quantile regressions (τ = 0.25, 0.5, 0.75)...")
    
    quantile_results = {}
    
    if X_list and aci_model is not None:
        y_aci_qr = df_model['ACI'].to_numpy()
        X_aci_qr = np.column_stack([df_model[feat].to_numpy() for feat in feature_names])
        X_aci_const = sm.add_constant(X_aci_qr)
        
        for tau in [0.25, 0.5, 0.75]:
            qr_model = QuantReg(y_aci_qr, X_aci_const)
            qr_results = qr_model.fit(q=tau, max_iter=2000)
            quantile_results[tau] = qr_results
            
            logger.info(f"Quantile τ={tau}: Pseudo R² = {qr_results.prsquared:.4f}")
    
    # Save results with metro-specific filename
    md_path = out_dir / f"analysis_summary_{metro.lower()}.md"
    
    with open(md_path, 'a') as f:
        f.write("## RQ3: Combined Affordability-Commute Index (ACI)\n\n")
        f.write("The ACI combines standardized rent burden and commute time:\n\n")
        f.write("```\n")
        f.write("ACI = z(rent_to_income) + z(commute_min_proxy)\n")
        f.write("```\n\n")
        f.write("Higher ACI values indicate greater combined pressure.\n\n")
        f.write(f"**ACI Statistics:** Mean = {df['ACI'].mean():.3f}, Std = {df['ACI'].std():.3f}, ")
        f.write(f"Min = {df['ACI'].min():.3f}, Max = {df['ACI'].max():.3f}\n\n")
    
    # Add ACI tier summary table
    tier_summary = df.group_by('ACI_tier').agg([
        pl.count().alias('n_zctas'),
        pl.col('ACI').mean().alias('mean_aci'),
        pl.col('ACI').min().alias('min_aci'),
        pl.col('ACI').max().alias('max_aci')
    ]).sort('ACI_tier')
    
    tier_table = {
        'ACI Tier': tier_summary['ACI_tier'].to_list(),
        'N ZCTAs': [str(n) for n in tier_summary['n_zctas'].to_list()],
        'Mean ACI': [f"{val:.3f}" for val in tier_summary['mean_aci'].to_list()],
        'Min ACI': [f"{val:.3f}" for val in tier_summary['min_aci'].to_list()],
        'Max ACI': [f"{val:.3f}" for val in tier_summary['max_aci'].to_list()]
    }
    
    save_markdown_table(tier_table, md_path, "ACI Tier Classification")
    
    if aci_model:
        coef_data = {
            'Variable': ['Intercept'] + feature_names,
            'Coefficient': [f"{val:.4f}" for val in aci_model['params']],
            'Std Error': [f"{val:.4f}" for val in aci_model['std_errors']],
            'p-value': [f"{val:.4f}" if val >= 0.0001 else '<0.0001' for val in aci_model['pvalues']]
        }
        
        save_markdown_table(coef_data, md_path, "RQ3: ACI OLS Model Coefficients")
    
    if quantile_results:
        with open(md_path, 'a') as f:
            f.write("### Quantile Regression Results\n\n")
        
        qr_data = {
            'Quantile (τ)': [],
            'Pseudo R²': [],
            'stops_per_km2 Coef': []
        }
        
        for tau, qr_res in quantile_results.items():
            qr_data['Quantile (τ)'].append(f"{tau:.2f}")
            qr_data['Pseudo R²'].append(f"{qr_res.prsquared:.4f}")
            
            if 'stops_per_km2' in feature_names:
                idx = feature_names.index('stops_per_km2') + 1
                qr_data['stops_per_km2 Coef'].append(f"{qr_res.params[idx]:.4f}")
            else:
                qr_data['stops_per_km2 Coef'].append('N/A')
        
        save_markdown_table(qr_data, md_path, "Quantile Regression Summary")
    
    # Visualizations
    
    # 1. ACI vs stops_per_km2 scatter
    if 'stops_per_km2' in df_model.columns:
        fig, ax = plt.subplots(figsize=(10, 6))
        
        x_transit = df_model['stops_per_km2'].to_numpy()
        y_aci_plot = df_model['ACI'].to_numpy()
        
        ax.scatter(x_transit, y_aci_plot, alpha=0.5, s=20)
        
        if aci_model and 'stops_per_km2' in feature_names:
            x_range = np.linspace(np.nanmin(x_transit), np.nanmax(x_transit), 100)
            
            idx = feature_names.index('stops_per_km2')
            slope = aci_model['params'][idx + 1]
            intercept = aci_model['params'][0]
            
            y_line = intercept + slope * x_range
            
            ax.plot(x_range, y_line, 'r-', linewidth=2, label='OLS Fit')
            ax.legend()
        
        ax.set_xlabel('Transit Stops per km²')
        ax.set_ylabel('ACI (Combined Pressure)')
        ax.set_title('ACI vs Transit Access')
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(fig_dir / f"rq3_{metro.lower()}_aci_transit.png", dpi=300, bbox_inches='tight')
        plt.close()
        
        logger.info("Saved ACI vs transit scatter")
    
    # 2. ACI boxplot by income segment
    if 'income_segment' in df.columns:
        fig, ax = plt.subplots(figsize=(10, 6))
        
        income_groups = [g for g in ['Low', 'Medium', 'High'] if g in df['income_segment'].unique().to_list()]
        aci_data = [
            df.filter(pl.col('income_segment') == group)['ACI'].to_numpy()
            for group in income_groups
        ]
        
        ax.boxplot(aci_data, labels=income_groups)
        ax.set_xlabel('Income Segment')
        ax.set_ylabel('ACI (Combined Pressure)')
        ax.set_title('ACI Distribution by Income Segment')
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(fig_dir / f"rq3_{metro.lower()}_aci_income.png", dpi=300, bbox_inches='tight')
        plt.close()
        
        logger.info("Saved ACI by income boxplot")
    
    # 2b. ACI boxplot by race group
    if 'majority_race' in df.columns:
        logger.info("Creating ACI by race boxplot...")
        
        race_groups = sorted(df['majority_race'].unique().drop_nulls().to_list())
        
        if len(race_groups) >= 2:
            fig, ax = plt.subplots(figsize=(10, 6))
            
            aci_race_data = []
            race_groups_filtered = []
            
            for group in race_groups:
                group_data = df.filter(pl.col('majority_race') == group)['ACI'].drop_nulls().to_numpy()
                if len(group_data) > 0:
                    aci_race_data.append(group_data)
                    race_groups_filtered.append(group)
            
            if len(race_groups_filtered) >= 2:
                ax.boxplot(aci_race_data, labels=race_groups_filtered)
                ax.set_xlabel('Majority Race')
                ax.set_ylabel('ACI (Combined Pressure)')
                ax.set_title('ACI Distribution by Majority Race')
                ax.grid(True, alpha=0.3)
                
                plt.tight_layout()
                plt.savefig(fig_dir / f"rq3_{metro.lower()}_aci_race.png", dpi=300, bbox_inches='tight')
                plt.close()
                
                logger.info("Saved ACI by race boxplot")
            else:
                logger.warning("Insufficient race groups with data for boxplot")
        else:
            logger.warning("Insufficient race diversity for race-based ACI boxplot")
    
    # 3. Choropleth map (if shapefile provided)
    if zcta_shp and zcta_shp.exists():
        try:
            import geopandas as gpd
            
            logger.info(f"Loading ZCTA shapefile: {zcta_shp}")
            gdf = gpd.read_file(zcta_shp)
            
            logger.info(f"Shapefile columns: {list(gdf.columns)}")
            
            df_map = df.select(['ZCTA5CE', 'ACI']).to_pandas()
            df_map['ZCTA5CE'] = df_map['ZCTA5CE'].astype(str)
            gdf['ZCTA5CE'] = gdf['ZCTA5CE'].astype(str)
            
            gdf_merged = gdf.merge(df_map, on='ZCTA5CE', how='inner')
            
            logger.info(f"Merged {len(gdf_merged)} ZCTAs for mapping")
            
            fig, ax = plt.subplots(figsize=(12, 10))
            
            gdf_merged.plot(
                column='ACI',
                cmap='RdYlBu_r',
                legend=True,
                ax=ax,
                edgecolor='black',
                linewidth=0.3,
                legend_kwds={'label': 'ACI (Combined Pressure)', 'shrink': 0.8}
            )
            
            ax.set_title(f'Affordability-Commute Index: {METRO_NAMES[metro]}')
            ax.axis('off')
            
            plt.tight_layout()
            plt.savefig(fig_dir / f"rq3_{metro.lower()}_aci_map.png", dpi=300, bbox_inches='tight')
            plt.close()
            
            logger.info("Saved ACI choropleth map")
            
        except ImportError as e:
            logger.warning(f"geopandas not available, skipping choropleth: {e}")
        except Exception as e:
            logger.error(f"Error creating choropleth: {e}")
            import traceback
            logger.error(traceback.format_exc())
    else:
        logger.info("No ZCTA shapefile provided, skipping choropleth map")
    
    # Interpretation
    with open(md_path, 'a') as f:
        f.write("#### Interpretation\n\n")
        
        if aci_model:
            f.write(f"The OLS model explains {aci_model['adj_r2']*100:.1f}% of variance in ACI ")
            f.write(f"(Adj R² = {aci_model['adj_r2']:.4f}). ")
            
            if 'stops_per_km2' in feature_names:
                idx = feature_names.index('stops_per_km2') + 1
                transit_coef = aci_model['params'][idx]
                transit_pval = aci_model['pvalues'][idx]
                
                if transit_pval < 0.05:
                    direction = "negative" if transit_coef < 0 else "positive"
                    f.write(f"Transit access has a statistically significant {direction} relationship with ACI ")
                    f.write(f"(β = {transit_coef:.4f}, p < 0.05), suggesting that ")
                    
                    if transit_coef < 0:
                        f.write("better transit access is associated with lower combined pressure.\n\n")
                    else:
                        f.write("transit access is associated with higher combined pressure (possibly due to location in high-demand areas).\n\n")
                else:
                    f.write(f"Transit access does not show a statistically significant relationship with ACI (p = {transit_pval:.4f}).\n\n")
        
        if quantile_results:
            f.write("Quantile regression reveals how predictors affect ACI differently across the distribution. ")
            f.write("Higher quantiles (τ = 0.75) represent ZCTAs with the highest combined pressure.\n\n")
        
        # APA-style figure captions
        f.write("### Figure Captions\n\n")
        
        fig_num = 1
        
        f.write(f"**Figure {fig_num}.** Affordability-Commute Index by transit stop density. ")
        f.write(f"Scatterplot shows the relationship between transit access (stops per km²) and combined housing-commute pressure ")
        f.write(f"with OLS regression line overlay. ")
        f.write(f"N = {len(df_model)} ZCTAs, {METRO_NAMES[metro]} metropolitan area.\n\n")
        fig_num += 1
        
        if 'income_segment' in df.columns:
            f.write(f"**Figure {fig_num}.** Affordability-Commute Index distribution by income segment. ")
            f.write(f"Boxplots compare ACI values across low, medium, and high income terciles. ")
            f.write(f"Higher values indicate greater combined pressure from rent burden and commute time. ")
            f.write(f"N = {df.shape[0]} ZCTAs, {METRO_NAMES[metro]} metropolitan area.\n\n")
            fig_num += 1
        
        if 'majority_race' in df.columns and len(df['majority_race'].unique().drop_nulls()) >= 2:
            f.write(f"**Figure {fig_num}.** Affordability-Commute Index distribution by majority race. ")
            f.write(f"Boxplots compare ACI values across ZCTAs grouped by racial majority (highest percentage). ")
            f.write(f"Shows potential disparities in combined housing-commute pressure by race. ")
            f.write(f"N = {df.shape[0]} ZCTAs, {METRO_NAMES[metro]} metropolitan area.\n\n")
            fig_num += 1
        
        if zcta_shp and zcta_shp.exists():
            f.write(f"**Figure {fig_num}.** Spatial distribution of Affordability-Commute Index. ")
            f.write(f"Choropleth map visualizes ACI values across ZIP Code Tabulation Areas (ZCTAs). ")
            f.write(f"Red tones indicate high combined pressure (high rent + long commute), ")
            f.write(f"blue tones indicate low pressure. ")
            f.write(f"{METRO_NAMES[metro]} metropolitan area.\n\n")
        
        f.write("---\n\n")
    
    # Save ACI data
    aci_df = df.select(['ZCTA5CE', 'rent_to_income', 'commute_min_proxy', 'rent_z', 'commute_z', 'ACI'])
    aci_df.write_csv(out_dir / f"rq3_aci_data_{metro.lower()}.csv")
    
    logger.info("RQ3 analysis complete")
