"""
RQ2: Equity Analysis Across Demographic Groups

This module examines how housing and commute burdens vary by income segment
and race using interaction models, group comparisons, ANOVA tests, and K-means
clustering to identify inequities in the housing-commute trade-off.

Author: DAT490 Team
Date: November 2025
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from scipy.stats import f_oneway
from sklearn.cluster import KMeans

from .models import fit_ols_robust
from .preprocessing import compute_majority_race
from .reporting import save_markdown_table

logger = logging.getLogger(__name__)


def run_rq2(df: pl.DataFrame, out_dir: Path, fig_dir: Path, metro: str) -> None:
    """
    RQ2: Equity analysis across demographic groups.
    
    Examines how housing and commute burdens vary by income segment using
    interaction models and group comparisons. Creates income terciles and
    tests for differential relationships.
    
    Parameters
    ----------
    df : pl.DataFrame
        Input DataFrame with ZCTA-level data containing demographic variables
        (income, race), rent_to_income, and commute metrics.
    out_dir : Path
        Output directory for results (markdown tables).
    fig_dir : Path
        Figure output directory for boxplots and cluster visualizations.
    metro : str
        Metro code (PHX, LA, DFW, MEM) for labeling outputs.
    
    Returns
    -------
    None
        Saves results to files in out_dir and fig_dir.
    
    Notes
    -----
    Analysis components:
    - Income tercile creation (Low/Medium/High)
    - Interaction model: rent ~ commute × low_income
    - ANOVA tests for group differences
    - K-means clustering (4 clusters)
    - Boxplots by income and race
    """
    logger.info("=" * 60)
    logger.info("RQ2: Equity Analysis")
    logger.info("=" * 60)
    
    # Initialize markdown path early with metro-specific filename
    md_path = out_dir / f"analysis_summary_{metro.lower()}.md"
    
    # Check for demographic columns
    demo_cols = ['pct_white', 'pct_black', 'pct_hispanic', 'pct_asian', 'median_income']
    missing_demo = [col for col in demo_cols if col not in df.columns]
    
    if len(missing_demo) == len(demo_cols):
        logger.warning("No demographic columns found, skipping RQ2")
        
        with open(md_path, 'a') as f:
            f.write("## RQ2: Equity Analysis\n\n")
            f.write("**Status:** Skipped - demographic columns not available in dataset.\n\n")
            f.write("---\n\n")
        return
    
    if missing_demo:
        logger.warning(f"Missing demographic columns: {missing_demo}")
    
    # Create income segments (terciles) if median_income exists
    if 'median_income' in df.columns and 'income_segment' not in df.columns:
        logger.info("Creating income terciles...")
        
        income_data = df.filter(pl.col('median_income').is_not_null())['median_income']
        q33 = income_data.quantile(0.333)
        q67 = income_data.quantile(0.667)
        
        df = df.with_columns(
            pl.when(pl.col('median_income') <= q33).then(pl.lit('Low'))
            .when(pl.col('median_income') <= q67).then(pl.lit('Medium'))
            .otherwise(pl.lit('High'))
            .alias('income_segment')
        )
        
        logger.info(f"Income tercile boundaries: Low ≤ ${q33:,.0f}, Medium ≤ ${q67:,.0f}, High > ${q67:,.0f}")
    
    # Create low_income indicator
    if 'income_segment' in df.columns:
        df = df.with_columns(
            (pl.col('income_segment') == 'Low').cast(pl.Int32).alias('low_income')
        )
    
    # Compute majority race using shared function to avoid code duplication
    df = compute_majority_race(df)
    
    # Interaction model
    model_interact = None
    
    if 'low_income' in df.columns:
        logger.info("Fitting interaction model...")
        
        df_model = df.filter(
            pl.col('rent_to_income').is_not_null() &
            pl.col('commute_min_proxy').is_not_null() &
            pl.col('low_income').is_not_null()
        )
        
        y = df_model['rent_to_income'].to_numpy()
        X_commute = df_model['commute_min_proxy'].to_numpy()
        X_low_inc = df_model['low_income'].to_numpy()
        X_interaction = X_commute * X_low_inc
        
        X_list = [X_commute, X_low_inc, X_interaction]
        feature_names = ['commute_min_proxy', 'low_income', 'commute×low_income']
        
        # Controls for RQ2: transit access, car ownership, and racial demographics
        # These capture structural inequalities in transportation and housing access
        for control_col in ['stops_per_km2', 'pct_car', 'pct_white', 'total_pop']:
            if control_col in df_model.columns:
                control_data = df_model[control_col].to_numpy()
                if not np.all(np.isnan(control_data)):
                    X_list.append(control_data)
                    feature_names.append(control_col)
        
        X = np.column_stack(X_list)
        model_interact = fit_ols_robust(y, X, feature_names)
        
        logger.info(f"Interaction Model - Adj R²: {model_interact['adj_r2']:.4f}, AIC: {model_interact['aic']:.2f}")
        
        with open(md_path, 'a') as f:
            f.write("## RQ2: Equity Analysis\n\n")
        
        coef_data = {
            'Variable': ['Intercept'] + feature_names,
            'Coefficient': [f"{val:.4f}" for val in model_interact['params']],
            'Std Error': [f"{val:.4f}" for val in model_interact['std_errors']],
            'p-value': [f"{val:.4f}" if val >= 0.0001 else '<0.0001' for val in model_interact['pvalues']]
        }
        
        save_markdown_table(coef_data, md_path, "RQ2: Interaction Model Coefficients")
    
    # Group comparisons
    if 'income_segment' in df.columns:
        logger.info("Performing group comparisons...")
        
        rent_by_income = df.group_by('income_segment').agg([
            pl.col('rent_to_income').mean().alias('mean_rent_burden'),
            pl.col('rent_to_income').std().alias('std_rent_burden'),
            pl.col('rent_to_income').count().alias('n')
        ]).sort('income_segment')
        
        logger.info("Rent burden by income segment:")
        logger.info(rent_by_income)
        
        # ANOVA: Test for significant differences across income segments
        logger.info("Performing ANOVA tests...")
        
        low_rent = df.filter(pl.col('income_segment') == 'Low')['rent_to_income'].drop_nulls().to_numpy()
        med_rent = df.filter(pl.col('income_segment') == 'Medium')['rent_to_income'].drop_nulls().to_numpy()
        high_rent = df.filter(pl.col('income_segment') == 'High')['rent_to_income'].drop_nulls().to_numpy()
        
        if len(low_rent) > 0 and len(med_rent) > 0 and len(high_rent) > 0:
            f_stat_rent, p_val_rent = f_oneway(low_rent, med_rent, high_rent)
            logger.info(f"ANOVA - Rent Burden: F={f_stat_rent:.3f}, p={p_val_rent:.4f}")
        else:
            f_stat_rent, p_val_rent = None, None
            logger.warning("Insufficient data for rent burden ANOVA")
        
        commute_by_income = None
        f_stat_commute, p_val_commute = None, None
        
        if 'long45_share' in df.columns:
            commute_by_income = df.group_by('income_segment').agg([
                pl.col('long45_share').mean().alias('mean_long45'),
                pl.col('long45_share').std().alias('std_long45'),
                pl.col('long45_share').count().alias('n')
            ]).sort('income_segment')
            
            logger.info("Long commute (45+ min) share by income segment:")
            logger.info(commute_by_income)
            
            # ANOVA for commute share
            low_commute = df.filter(pl.col('income_segment') == 'Low')['long45_share'].drop_nulls().to_numpy()
            med_commute = df.filter(pl.col('income_segment') == 'Medium')['long45_share'].drop_nulls().to_numpy()
            high_commute = df.filter(pl.col('income_segment') == 'High')['long45_share'].drop_nulls().to_numpy()
            
            if len(low_commute) > 0 and len(med_commute) > 0 and len(high_commute) > 0:
                f_stat_commute, p_val_commute = f_oneway(low_commute, med_commute, high_commute)
                logger.info(f"ANOVA - Long Commute Share: F={f_stat_commute:.3f}, p={p_val_commute:.4f}")
        
        # ANOVA for transit density if available
        f_stat_transit, p_val_transit = None, None
        if 'stops_per_km2' in df.columns:
            low_transit = df.filter(pl.col('income_segment') == 'Low')['stops_per_km2'].drop_nulls().to_numpy()
            med_transit = df.filter(pl.col('income_segment') == 'Medium')['stops_per_km2'].drop_nulls().to_numpy()
            high_transit = df.filter(pl.col('income_segment') == 'High')['stops_per_km2'].drop_nulls().to_numpy()
            
            if len(low_transit) > 0 and len(med_transit) > 0 and len(high_transit) > 0:
                f_stat_transit, p_val_transit = f_oneway(low_transit, med_transit, high_transit)
                logger.info(f"ANOVA - Transit Density: F={f_stat_transit:.3f}, p={p_val_transit:.4f}")
        
        # Create boxplots
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        
        income_groups = df['income_segment'].unique().to_list()
        income_groups = [g for g in ['Low', 'Medium', 'High'] if g in income_groups]
        
        rent_data = [
            df.filter(pl.col('income_segment') == group)['rent_to_income'].to_numpy()
            for group in income_groups
        ]
        
        axes[0].boxplot(rent_data, labels=income_groups)
        axes[0].set_xlabel('Income Segment')
        axes[0].set_ylabel('Rent-to-Income Ratio')
        axes[0].set_title('Rent Burden by Income Segment')
        axes[0].grid(True, alpha=0.3)
        
        if 'long45_share' in df.columns:
            commute_data = [
                df.filter(pl.col('income_segment') == group)['long45_share'].to_numpy()
                for group in income_groups
            ]
            
            axes[1].boxplot(commute_data, labels=income_groups)
            axes[1].set_xlabel('Income Segment')
            axes[1].set_ylabel('Share with 45+ min Commute')
            axes[1].set_title('Long Commute Share by Income Segment')
            axes[1].grid(True, alpha=0.3)
        else:
            commute_data = [
                df.filter(pl.col('income_segment') == group)['commute_min_proxy'].to_numpy()
                for group in income_groups
            ]
            
            axes[1].boxplot(commute_data, labels=income_groups)
            axes[1].set_xlabel('Income Segment')
            axes[1].set_ylabel('Commute Time (minutes)')
            axes[1].set_title('Commute Time by Income Segment')
            axes[1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(fig_dir / f"rq2_{metro.lower()}_boxplots.png", dpi=300, bbox_inches='tight')
        plt.close()
        
        logger.info("Saved RQ2 income boxplots")
        
        # Race-based boxplots if majority_race column exists
        if 'majority_race' in df.columns:
            logger.info("Creating race-based boxplots...")
            
            race_groups = df['majority_race'].unique().drop_nulls().to_list()
            race_groups = sorted(race_groups)
            
            if len(race_groups) >= 2:
                fig_race, ax_race = plt.subplots(figsize=(10, 6))
                
                race_rent_data = [
                    df.filter(pl.col('majority_race') == group)['rent_to_income'].drop_nulls().to_numpy()
                    for group in race_groups
                ]
                
                # Only plot groups with data
                race_rent_data_filtered = []
                race_groups_filtered = []
                for group, data in zip(race_groups, race_rent_data):
                    if len(data) > 0:
                        race_rent_data_filtered.append(data)
                        race_groups_filtered.append(group)
                
                if len(race_groups_filtered) >= 2:
                    ax_race.boxplot(race_rent_data_filtered, labels=race_groups_filtered)
                    ax_race.set_xlabel('Majority Race')
                    ax_race.set_ylabel('Rent-to-Income Ratio')
                    ax_race.set_title('Rent Burden by Majority Race')
                    ax_race.grid(True, alpha=0.3)
                    
                    plt.tight_layout()
                    plt.savefig(fig_dir / f"rq2_{metro.lower()}_boxplots_race.png", dpi=300, bbox_inches='tight')
                    plt.close()
                    
                    logger.info("Saved RQ2 race-based boxplots")
                    
                    # ANOVA for race groups
                    if len(race_rent_data_filtered) >= 3:
                        f_stat_race, p_val_race = f_oneway(*race_rent_data_filtered)
                        logger.info(f"ANOVA - Rent Burden by Race: F={f_stat_race:.3f}, p={p_val_race:.4f}")
                    else:
                        f_stat_race, p_val_race = None, None
                        logger.info("Insufficient race groups for ANOVA")
                else:
                    f_stat_race, p_val_race = None, None
                    logger.warning("Insufficient data for race-based boxplots")
            else:
                f_stat_race, p_val_race = None, None
                logger.warning("Insufficient race diversity for analysis")
        else:
            f_stat_race, p_val_race = None, None
        
        # Save group statistics
        with open(md_path, 'a') as f:
            f.write("### Group Comparisons\n\n")
        
        rent_stats = {
            'Income Segment': rent_by_income['income_segment'].to_list(),
            'Mean Rent Burden': [f"{val:.3f}" for val in rent_by_income['mean_rent_burden'].to_list()],
            'Std Dev': [f"{val:.3f}" for val in rent_by_income['std_rent_burden'].to_list()],
            'N': [str(val) for val in rent_by_income['n'].to_list()]
        }
        
        save_markdown_table(rent_stats, md_path, "Rent Burden by Income Segment")
        
        if 'long45_share' in df.columns and commute_by_income is not None:
            commute_stats = {
                'Income Segment': commute_by_income['income_segment'].to_list(),
                'Mean Long45 Share': [f"{val:.3f}" for val in commute_by_income['mean_long45'].to_list()],
                'Std Dev': [f"{val:.3f}" for val in commute_by_income['std_long45'].to_list()],
                'N': [str(val) for val in commute_by_income['n'].to_list()]
            }
            
            save_markdown_table(commute_stats, md_path, "Long Commute Share by Income Segment")
        
        # K-Means clustering (optional): Cluster ZCTAs into affordability/commute zones
        logger.info("Performing K-Means clustering...")
        
        df_cluster = df.filter(
            pl.col('rent_to_income').is_not_null() & 
            pl.col('commute_min_proxy').is_not_null()
        )
        
        if len(df_cluster) >= 10:  # Need sufficient data for clustering
            # Standardize features for K-means (equal weighting of dimensions)
            rent_vals = df_cluster['rent_to_income'].to_numpy()
            commute_vals = df_cluster['commute_min_proxy'].to_numpy()
            
            rent_mean, rent_std = rent_vals.mean(), rent_vals.std()
            commute_mean, commute_std = commute_vals.mean(), commute_vals.std()
            
            rent_z = (rent_vals - rent_mean) / rent_std
            commute_z = (commute_vals - commute_mean) / commute_std
            
            X_cluster = np.column_stack([rent_z, commute_z])
            
            logger.info(f"Standardized features - Rent: μ={rent_mean:.3f}, σ={rent_std:.3f}; Commute: μ={commute_mean:.1f}, σ={commute_std:.1f}")
            
            # Fit K-Means with 4 clusters
            try:
                kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
                cluster_labels = kmeans.fit_predict(X_cluster)
            except (AttributeError, Exception) as e:
                logger.warning(f"K-means clustering failed (library compatibility issue): {e}")
                logger.warning("Skipping K-means clustering analysis")
                kmeans = None
                cluster_labels = None
            
            # Only proceed with clustering visualization if successful
            if kmeans is not None and cluster_labels is not None:
                # Add cluster labels to filtered dataframe
                df_cluster = df_cluster.with_columns(
                    pl.Series('cluster', cluster_labels)
                )
                
                # Compute cluster summaries
                cluster_summary = df_cluster.group_by('cluster').agg([
                    pl.col('rent_to_income').mean().alias('mean_rent_burden'),
                    pl.col('commute_min_proxy').mean().alias('mean_commute'),
                    pl.col('rent_to_income').count().alias('n_zctas')
                ]).sort('cluster')
                
                logger.info("Cluster summary:")
                logger.info(cluster_summary)
                
                # Save cluster summary to markdown
                cluster_stats = {
                    'Cluster': [f"Cluster {i}" for i in cluster_summary['cluster'].to_list()],
                    'Mean Rent Burden': [f"{val:.3f}" for val in cluster_summary['mean_rent_burden'].to_list()],
                    'Mean Commute (min)': [f"{val:.1f}" for val in cluster_summary['mean_commute'].to_list()],
                    'N ZCTAs': [str(val) for val in cluster_summary['n_zctas'].to_list()]
                }
                
                save_markdown_table(cluster_stats, md_path, "K-Means Clusters (Affordability/Commute Zones)")
                
                # Visualize clusters
                fig_cluster, ax_cluster = plt.subplots(figsize=(10, 8))
                
                scatter = ax_cluster.scatter(
                    df_cluster['commute_min_proxy'],
                    df_cluster['rent_to_income'],
                    c=cluster_labels,
                    cmap='viridis',
                    alpha=0.6,
                    edgecolors='black',
                    linewidths=0.5
                )
                
                # Plot cluster centroids
                centroids = kmeans.cluster_centers_
                ax_cluster.scatter(
                    centroids[:, 1],
                    centroids[:, 0],
                    c='red',
                    marker='X',
                    s=300,
                    edgecolors='black',
                    linewidths=2,
                    label='Centroids'
                )
                
                ax_cluster.set_xlabel('Commute Time (minutes)')
                ax_cluster.set_ylabel('Rent-to-Income Ratio')
                ax_cluster.set_title('K-Means Clusters: Affordability-Commute Zones')
                ax_cluster.legend()
                ax_cluster.grid(True, alpha=0.3)
                
                plt.colorbar(scatter, ax=ax_cluster, label='Cluster')
                plt.tight_layout()
                plt.savefig(fig_dir / f"rq2_{metro.lower()}_clusters.png", dpi=300, bbox_inches='tight')
                plt.close()
                
                logger.info("Saved K-Means cluster visualization")
        else:
            logger.warning("Insufficient data for K-Means clustering")
        
        # ANOVA Results Summary
        with open(md_path, 'a') as f:
            f.write("### ANOVA Results\n\n")
            
            anova_vars = []
            anova_fstats = []
            anova_pvals = []
            anova_sig = []
            
            if f_stat_rent is not None and p_val_rent is not None:
                anova_vars.append('Rent Burden')
                anova_fstats.append(f"{f_stat_rent:.3f}")
                anova_pvals.append(f"{p_val_rent:.4f}" if p_val_rent >= 0.0001 else '<0.0001')
                anova_sig.append('Yes' if p_val_rent < 0.05 else 'No')
            
            if f_stat_commute is not None and p_val_commute is not None:
                anova_vars.append('Long Commute Share')
                anova_fstats.append(f"{f_stat_commute:.3f}")
                anova_pvals.append(f"{p_val_commute:.4f}" if p_val_commute >= 0.0001 else '<0.0001')
                anova_sig.append('Yes' if p_val_commute < 0.05 else 'No')
            
            if f_stat_transit is not None and p_val_transit is not None:
                anova_vars.append('Transit Density')
                anova_fstats.append(f"{f_stat_transit:.3f}")
                anova_pvals.append(f"{p_val_transit:.4f}" if p_val_transit >= 0.0001 else '<0.0001')
                anova_sig.append('Yes' if p_val_transit < 0.05 else 'No')
            
            if 'f_stat_race' in locals() and f_stat_race is not None and p_val_race is not None:
                anova_vars.append('Rent Burden by Race')
                anova_fstats.append(f"{f_stat_race:.3f}")
                anova_pvals.append(f"{p_val_race:.4f}" if p_val_race >= 0.0001 else '<0.0001')
                anova_sig.append('Yes' if p_val_race < 0.05 else 'No')
            
            if anova_vars:
                anova_results = {
                    'Variable': anova_vars,
                    'F-statistic': anova_fstats,
                    'p-value': anova_pvals,
                    'Significant (α=0.05)': anova_sig
                }
                save_markdown_table(anova_results, md_path, "ANOVA: Group Comparisons Across Income Segments")
            else:
                f.write("*No ANOVA tests performed (insufficient data)*\n\n")
        
        # Interpretation
        with open(md_path, 'a') as f:
            f.write("#### Interpretation\n\n")
            
            # Interaction model interpretation
            if 'low_income' in df.columns and model_interact:
                interaction_pval = model_interact['pvalues'][3] if len(model_interact['pvalues']) > 3 else 1.0
                
                if interaction_pval < 0.05:
                    f.write("**Interaction Effect:** The interaction between commute time and low-income status is statistically significant ")
                    f.write("(p < 0.05), suggesting that the relationship between commute and rent burden differs ")
                    f.write("for low-income areas. This indicates potential inequity in the affordability-commute trade-off.\n\n")
                else:
                    f.write("**Interaction Effect:** The interaction between commute time and low-income status is not statistically significant ")
                    f.write(f"(p = {interaction_pval:.4f}), suggesting the commute-rent relationship is similar across income groups.\n\n")
            
            # ANOVA interpretation
            if f_stat_rent is not None and p_val_rent is not None:
                if p_val_rent < 0.05:
                    f.write("**Income Disparities:** ANOVA confirms statistically significant differences in rent burden across income segments ")
                    f.write(f"(F={f_stat_rent:.2f}, p={p_val_rent:.4f}), indicating income-based inequity in housing affordability.\n\n")
                else:
                    f.write("**Income Disparities:** ANOVA found no significant differences in rent burden across income segments ")
                    f.write(f"(F={f_stat_rent:.2f}, p={p_val_rent:.4f}).\n\n")
            
            # Race-based interpretation
            if 'f_stat_race' in locals() and f_stat_race is not None and p_val_race is not None:
                if p_val_race < 0.05:
                    f.write("**Racial Disparities:** ANOVA reveals statistically significant differences in rent burden across racial majority groups ")
                    f.write(f"(F={f_stat_race:.2f}, p={p_val_race:.4f}), suggesting race-based inequities in housing affordability.\n\n")
                else:
                    f.write("**Racial Disparities:** No significant racial differences detected in rent burden ")
                    f.write(f"(F={f_stat_race:.2f}, p={p_val_race:.4f}).\n\n")
            
            # Clustering interpretation
            f.write("**K-Means Clustering:** ZCTAs were grouped into four affordability-commute zones based on ")
            f.write("rent burden and commute time patterns. These clusters reveal distinct neighborhood typologies ")
            f.write("(e.g., high-rent/short-commute vs. low-rent/long-commute zones).\n\n")
            
            # Figure references
            f.write(f"**Figures:** `rq2_{metro.lower()}_boxplots.png`, ")
            if 'majority_race' in df.columns:
                f.write(f"`rq2_{metro.lower()}_boxplots_race.png`, ")
            f.write(f"`rq2_{metro.lower()}_clusters.png`\n\n")
            f.write("---\n\n")
    
    logger.info("RQ2 analysis complete")
