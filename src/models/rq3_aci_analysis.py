"""RQ3: Combined Affordability-Commute Index (ACI) Analysis.

This module computes the Affordability-Commute Index (ACI) as the sum of
standardized rent burden and commute time, performs OLS and quantile regression
modeling, and generates visualizations including optional choropleth maps.
"""
from __future__ import annotations

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
from .results import RQ3Results

logger = logging.getLogger(__name__)


def analyze_rq3(df: pl.DataFrame) -> RQ3Results:
    """Compute ACI and fit OLS + quantile regression models.

    Parameters
    ----------
    df : pl.DataFrame
        Input DataFrame with rent_to_income and commute_min_proxy columns.

    Returns
    -------
    RQ3Results
        Typed container with ACI model, quantile results, tier summary.
    """
    logger.info("=" * 60)
    logger.info("RQ3: Combined Affordability-Commute Index (ACI)")
    logger.info("=" * 60)

    # Compute ACI = z(rent_to_income) + z(commute_min_proxy)
    rent_mean = df['rent_to_income'].mean()
    rent_std = df['rent_to_income'].std()
    commute_mean = df['commute_min_proxy'].mean()
    commute_std = df['commute_min_proxy'].std()

    df = df.with_columns([
        ((pl.col('rent_to_income') - rent_mean) / rent_std).alias('rent_z'),
        ((pl.col('commute_min_proxy') - commute_mean) / commute_std).alias('commute_z'),
    ])
    df = df.with_columns(
        (pl.col('rent_z') + pl.col('commute_z')).alias('ACI')
    )
    logger.info(f"ACI computed. Mean: {df['ACI'].mean():.3f}, Std: {df['ACI'].std():.3f}")

    # Classify into ACI tiers (terciles)
    aci_q33 = df['ACI'].quantile(0.333)
    aci_q67 = df['ACI'].quantile(0.667)

    df = df.with_columns(
        pl.when(pl.col('ACI') <= aci_q33).then(pl.lit('Low'))
        .when(pl.col('ACI') <= aci_q67).then(pl.lit('Medium'))
        .otherwise(pl.lit('High'))
        .alias('ACI_tier')
    )

    tier_summary = df.group_by('ACI_tier').agg([
        pl.count().alias('n_zctas'),
        pl.col('ACI').mean().alias('mean_aci'),
        pl.col('ACI').min().alias('min_aci'),
        pl.col('ACI').max().alias('max_aci'),
    ]).sort('ACI_tier')

    # Compute majority race if not present
    if 'majority_race' not in df.columns:
        df = compute_majority_race(df)

    # OLS: ACI ~ stops_per_km2 + zori + controls
    df_model = df.filter(pl.col('ACI').is_not_null())
    feature_candidates = []

    if 'stops_per_km2' in df_model.columns:
        feature_candidates.append('stops_per_km2')
    if 'zori' in df_model.columns:
        feature_candidates.append('zori')
    for col in ['median_income', 'pct_transit', 'pct_drive_alone', 'total_pop']:
        if col in df_model.columns:
            feature_candidates.append(col)

    aci_model = None
    cv_rmse_aci = None
    feature_names: list[str] = []

    if feature_candidates:
        filter_expr = pl.col('ACI').is_not_null()
        for feat in feature_candidates:
            filter_expr = filter_expr & pl.col(feat).is_not_null()
        df_model = df_model.filter(filter_expr)

        logger.info(f"Complete cases for OLS: {df_model.shape[0]}")

        if df_model.shape[0] >= 10:
            y_aci = df_model['ACI'].to_numpy()
            x_list = []

            for feat in feature_candidates:
                x_col = df_model[feat].to_numpy()
                if not np.any(np.isnan(x_col)) and not np.any(np.isinf(x_col)):
                    x_list.append(x_col)
                    feature_names.append(feat)

            if x_list:
                x_aci = np.column_stack(x_list)
                aci_model = fit_ols_robust(y_aci, x_aci, feature_names)
                cv_rmse_aci, _ = cv_rmse(x_aci, y_aci, k=5)
                logger.info(f"ACI OLS - Adj R2: {aci_model['adj_r2']:.4f}, "
                            f"CV-RMSE: {cv_rmse_aci:.4f}")

    # Quantile regression
    quantile_results: dict[float, object] = {}
    if feature_names and aci_model is not None:
        logger.info("Fitting quantile regressions (tau = 0.25, 0.5, 0.75)...")
        y_aci_qr = df_model['ACI'].to_numpy()
        x_aci_qr = np.column_stack([df_model[feat].to_numpy() for feat in feature_names])
        x_aci_const = sm.add_constant(x_aci_qr)

        for tau in [0.25, 0.5, 0.75]:
            qr_model = QuantReg(y_aci_qr, x_aci_const)
            qr_results = qr_model.fit(q=tau, max_iter=2000)
            quantile_results[tau] = qr_results
            logger.info(f"Quantile tau={tau}: Pseudo R2 = {qr_results.prsquared:.4f}")

    return RQ3Results(
        aci_model=aci_model,
        quantile_results=quantile_results,
        cv_rmse_aci=cv_rmse_aci,
        tier_summary=tier_summary,
        feature_names=feature_names,
        df_with_aci=df,
    )


def _plot_aci_transit(
    df_model: pl.DataFrame,
    aci_model: Optional[dict],
    feature_names: list[str],
    fig_dir: Path,
    metro: str,
) -> None:
    """ACI vs transit density scatter with OLS fit line."""
    if 'stops_per_km2' not in df_model.columns:
        return

    fig, ax = plt.subplots(figsize=(10, 6))

    x_transit = df_model['stops_per_km2'].to_numpy()
    y_aci = df_model['ACI'].to_numpy()
    ax.scatter(x_transit, y_aci, alpha=0.5, s=20)

    if aci_model and 'stops_per_km2' in feature_names:
        x_range = np.linspace(np.nanmin(x_transit), np.nanmax(x_transit), 100)
        idx = feature_names.index('stops_per_km2')
        slope = aci_model['params'][idx + 1]
        intercept = aci_model['params'][0]
        ax.plot(x_range, intercept + slope * x_range, 'r-', linewidth=2, label='OLS Fit')
        ax.legend()

    ax.set_xlabel('Transit Stops per km2')
    ax.set_ylabel('ACI (Combined Pressure)')
    ax.set_title('ACI vs Transit Access')
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(fig_dir / f"rq3_{metro.lower()}_aci_transit.png", dpi=300, bbox_inches='tight')
    plt.close()


def _plot_aci_boxplots(
    df: pl.DataFrame,
    fig_dir: Path,
    metro: str,
) -> None:
    """ACI boxplots by income segment and race."""
    if 'income_segment' in df.columns:
        income_groups = [g for g in ['Low', 'Medium', 'High']
                         if g in df['income_segment'].unique().to_list()]
        aci_data = [
            df.filter(pl.col('income_segment') == g)['ACI'].to_numpy()
            for g in income_groups
        ]

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.boxplot(aci_data, labels=income_groups)
        ax.set_xlabel('Income Segment')
        ax.set_ylabel('ACI (Combined Pressure)')
        ax.set_title('ACI Distribution by Income Segment')
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(fig_dir / f"rq3_{metro.lower()}_aci_income.png", dpi=300, bbox_inches='tight')
        plt.close()

    if 'majority_race' in df.columns:
        race_groups = sorted(df['majority_race'].unique().drop_nulls().to_list())
        race_data = []
        race_labels = []
        for group in race_groups:
            data = df.filter(pl.col('majority_race') == group)['ACI'].drop_nulls().to_numpy()
            if len(data) > 0:
                race_data.append(data)
                race_labels.append(group)

        if len(race_labels) >= 2:
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.boxplot(race_data, labels=race_labels)
            ax.set_xlabel('Majority Race')
            ax.set_ylabel('ACI (Combined Pressure)')
            ax.set_title('ACI Distribution by Majority Race')
            ax.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(fig_dir / f"rq3_{metro.lower()}_aci_race.png",
                        dpi=300, bbox_inches='tight')
            plt.close()


def _plot_aci_choropleth(
    df: pl.DataFrame,
    zcta_shp: Path,
    fig_dir: Path,
    metro: str,
) -> None:
    """Generate ACI choropleth map from ZCTA shapefile."""
    try:
        import geopandas as gpd

        logger.info(f"Loading ZCTA shapefile: {zcta_shp}")
        gdf = gpd.read_file(zcta_shp)

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
            legend_kwds={'label': 'ACI (Combined Pressure)', 'shrink': 0.8},
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


def report_rq3(
    results: RQ3Results,
    out_dir: Path,
    fig_dir: Path,
    metro: str,
    zcta_shp: Optional[Path] = None,
) -> None:
    """Write RQ3 results to markdown and generate visualizations.

    Parameters
    ----------
    results : RQ3Results
        Output from analyze_rq3().
    out_dir : Path
        Markdown output directory.
    fig_dir : Path
        Figure output directory.
    metro : str
        Metro code for file naming.
    zcta_shp : Path, optional
        Path to ZCTA shapefile for choropleth map.
    """
    df = results.df_with_aci
    md_path = out_dir / f"analysis_summary_{metro.lower()}.md"

    with open(md_path, 'a') as f:
        f.write("## RQ3: Combined Affordability-Commute Index (ACI)\n\n")
        f.write("The ACI combines standardized rent burden and commute time:\n\n")
        f.write("```\nACI = z(rent_to_income) + z(commute_min_proxy)\n```\n\n")
        f.write("Higher ACI values indicate greater combined pressure.\n\n")
        f.write(f"**ACI Statistics:** Mean = {df['ACI'].mean():.3f}, "
                f"Std = {df['ACI'].std():.3f}, "
                f"Min = {df['ACI'].min():.3f}, Max = {df['ACI'].max():.3f}\n\n")

    # Tier summary table
    if results.tier_summary is not None:
        ts = results.tier_summary
        tier_table = {
            'ACI Tier': ts['ACI_tier'].to_list(),
            'N ZCTAs': [str(n) for n in ts['n_zctas'].to_list()],
            'Mean ACI': [f"{val:.3f}" for val in ts['mean_aci'].to_list()],
            'Min ACI': [f"{val:.3f}" for val in ts['min_aci'].to_list()],
            'Max ACI': [f"{val:.3f}" for val in ts['max_aci'].to_list()],
        }
        save_markdown_table(tier_table, md_path, "ACI Tier Classification")

    # OLS coefficients
    if results.aci_model:
        coef_data = {
            'Variable': ['Intercept'] + results.feature_names,
            'Coefficient': [f"{val:.4f}" for val in results.aci_model['params']],
            'Std Error': [f"{val:.4f}" for val in results.aci_model['std_errors']],
            'p-value': [f"{val:.4f}" if val >= 0.0001 else '<0.0001'
                        for val in results.aci_model['pvalues']],
        }
        save_markdown_table(coef_data, md_path, "RQ3: ACI OLS Model Coefficients")

    # Quantile regression table
    if results.quantile_results:
        with open(md_path, 'a') as f:
            f.write("### Quantile Regression Results\n\n")

        qr_data: dict[str, list[str]] = {
            'Quantile (tau)': [],
            'Pseudo R2': [],
            'stops_per_km2 Coef': [],
        }
        for tau, qr_res in results.quantile_results.items():
            qr_data['Quantile (tau)'].append(f"{tau:.2f}")
            qr_data['Pseudo R2'].append(f"{qr_res.prsquared:.4f}")

            if 'stops_per_km2' in results.feature_names:
                idx = results.feature_names.index('stops_per_km2') + 1
                qr_data['stops_per_km2 Coef'].append(f"{qr_res.params[idx]:.4f}")
            else:
                qr_data['stops_per_km2 Coef'].append('N/A')

        save_markdown_table(qr_data, md_path, "Quantile Regression Summary")

    # Visualizations
    df_model = df.filter(pl.col('ACI').is_not_null())
    _plot_aci_transit(df_model, results.aci_model, results.feature_names, fig_dir, metro)
    _plot_aci_boxplots(df, fig_dir, metro)

    if zcta_shp and zcta_shp.exists():
        _plot_aci_choropleth(df, zcta_shp, fig_dir, metro)

    # Interpretation
    with open(md_path, 'a') as f:
        f.write("#### Interpretation\n\n")

        if results.aci_model:
            f.write(f"The OLS model explains {results.aci_model['adj_r2']*100:.1f}% "
                    f"of variance in ACI (Adj R2 = {results.aci_model['adj_r2']:.4f}). ")

            if 'stops_per_km2' in results.feature_names:
                idx = results.feature_names.index('stops_per_km2') + 1
                transit_coef = results.aci_model['params'][idx]
                transit_pval = results.aci_model['pvalues'][idx]

                if transit_pval < 0.05:
                    direction = "negative" if transit_coef < 0 else "positive"
                    f.write(f"Transit access has a significant {direction} relationship "
                            f"with ACI (B = {transit_coef:.4f}, p < 0.05).\n\n")
                else:
                    f.write("Transit access is not significantly related to ACI "
                            f"(p = {transit_pval:.4f}).\n\n")

        if results.quantile_results:
            f.write("Quantile regression reveals how predictors affect ACI "
                    "differently across the distribution.\n\n")

        f.write("### Figure Captions\n\n")
        fig_num = 1

        f.write(f"**Figure {fig_num}.** ACI by transit stop density. "
                f"N = {df_model.shape[0]} ZCTAs, {METRO_NAMES[metro]}.\n\n")
        fig_num += 1

        if 'income_segment' in df.columns:
            f.write(f"**Figure {fig_num}.** ACI distribution by income segment. "
                    f"N = {df.shape[0]} ZCTAs, {METRO_NAMES[metro]}.\n\n")
            fig_num += 1

        if ('majority_race' in df.columns
                and len(df['majority_race'].unique().drop_nulls()) >= 2):
            f.write(f"**Figure {fig_num}.** ACI distribution by majority race. "
                    f"N = {df.shape[0]} ZCTAs, {METRO_NAMES[metro]}.\n\n")
            fig_num += 1

        if zcta_shp and zcta_shp.exists():
            f.write(f"**Figure {fig_num}.** Spatial distribution of ACI. "
                    f"{METRO_NAMES[metro]}.\n\n")

        f.write("---\n\n")

    # Save ACI data CSV
    aci_df = df.select(['ZCTA5CE', 'rent_to_income', 'commute_min_proxy',
                         'rent_z', 'commute_z', 'ACI'])
    aci_df.write_csv(out_dir / f"rq3_aci_data_{metro.lower()}.csv")

    logger.info("RQ3 results saved")


def run_rq3(
    df: pl.DataFrame,
    out_dir: Path,
    fig_dir: Path,
    metro: str,
    zcta_shp: Optional[Path] = None,
) -> None:
    """RQ3: Combined pressure analysis (full pipeline).

    Delegates to analyze_rq3() and report_rq3() for separation of concerns.

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
    zcta_shp : Path, optional
        Path to ZCTA shapefile for choropleth map.
    """
    results = analyze_rq3(df)
    report_rq3(results, out_dir, fig_dir, metro, zcta_shp=zcta_shp)
