"""RQ2: Equity Analysis Across Demographic Groups.

This module examines how housing and commute burdens vary by income segment
and race using interaction models, group comparisons, ANOVA tests, and K-means
clustering to identify inequities in the housing-commute trade-off.
"""
from __future__ import annotations

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from sklearn.cluster import KMeans

from .models import anova_by_group, fit_ols_robust
from .preprocessing import compute_majority_race
from .reporting import save_markdown_table
from .results import RQ2Results

logger = logging.getLogger(__name__)


def analyze_rq2(df: pl.DataFrame) -> RQ2Results:
    """Perform RQ2 equity analysis without any I/O.

    Creates income segments, fits an interaction model, runs ANOVA tests,
    and performs K-means clustering on rent burden and commute time.

    Parameters
    ----------
    df : pl.DataFrame
        Input DataFrame with ZCTA-level data containing demographic variables
        (income, race), rent_to_income, and commute metrics.

    Returns
    -------
    RQ2Results
        Typed container with interaction model, group stats, ANOVA, clusters.
    """
    logger.info("=" * 60)
    logger.info("RQ2: Equity Analysis")
    logger.info("=" * 60)

    # Check for demographic columns
    demo_cols = ['pct_white', 'pct_black', 'pct_hispanic', 'pct_asian', 'median_income']
    missing_demo = [col for col in demo_cols if col not in df.columns]

    if len(missing_demo) == len(demo_cols):
        logger.warning("No demographic columns found, skipping RQ2")
        return RQ2Results()

    if missing_demo:
        logger.warning(f"Missing demographic columns: {missing_demo}")

    # Create income segments (terciles) if needed
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
        logger.info(f"Income tercile boundaries: Low <= ${q33:,.0f}, Medium <= ${q67:,.0f}")

    # Create low_income indicator
    if 'income_segment' in df.columns:
        df = df.with_columns(
            (pl.col('income_segment') == 'Low').cast(pl.Int32).alias('low_income')
        )

    # Compute majority race
    df = compute_majority_race(df)

    # Interaction model
    interaction_model = None
    if 'low_income' in df.columns:
        logger.info("Fitting interaction model...")
        df_model = df.filter(
            pl.col('rent_to_income').is_not_null()
            & pl.col('commute_min_proxy').is_not_null()
            & pl.col('low_income').is_not_null()
        )

        y = df_model['rent_to_income'].to_numpy()
        x_commute = df_model['commute_min_proxy'].to_numpy()
        x_low_inc = df_model['low_income'].to_numpy()
        x_interaction = x_commute * x_low_inc

        x_list = [x_commute, x_low_inc, x_interaction]
        feature_names = ['commute_min_proxy', 'low_income', 'commute*low_income']

        for control_col in ['stops_per_km2', 'pct_car', 'pct_white', 'total_pop']:
            if control_col in df_model.columns:
                control_data = df_model[control_col].to_numpy()
                if not np.all(np.isnan(control_data)):
                    x_list.append(control_data)
                    feature_names.append(control_col)

        x_arr = np.column_stack(x_list)
        interaction_model = fit_ols_robust(y, x_arr, feature_names)
        logger.info(f"Interaction Model - Adj R2: {interaction_model['adj_r2']:.4f}")

    # Group comparisons
    rent_by_income = None
    commute_by_income = None
    anova_results = []

    if 'income_segment' in df.columns:
        logger.info("Performing group comparisons...")

        rent_by_income = df.group_by('income_segment').agg([
            pl.col('rent_to_income').mean().alias('mean_rent_burden'),
            pl.col('rent_to_income').std().alias('std_rent_burden'),
            pl.col('rent_to_income').count().alias('n'),
        ]).sort('income_segment')

        # ANOVA tests using the shared helper
        income_groups = ['Low', 'Medium', 'High']

        anova_results.append(
            anova_by_group(df, 'rent_to_income', 'income_segment', income_groups)
        )

        if 'long45_share' in df.columns:
            commute_by_income = df.group_by('income_segment').agg([
                pl.col('long45_share').mean().alias('mean_long45'),
                pl.col('long45_share').std().alias('std_long45'),
                pl.col('long45_share').count().alias('n'),
            ]).sort('income_segment')

            anova_results.append(
                anova_by_group(df, 'long45_share', 'income_segment', income_groups)
            )

        if 'stops_per_km2' in df.columns:
            anova_results.append(
                anova_by_group(df, 'stops_per_km2', 'income_segment', income_groups)
            )

        # Race-based ANOVA
        if 'majority_race' in df.columns:
            race_groups = sorted(df['majority_race'].unique().drop_nulls().to_list())
            if len(race_groups) >= 2:
                anova_results.append(
                    anova_by_group(df, 'rent_to_income', 'majority_race', race_groups)
                )

    # K-Means clustering
    cluster_summary = None
    cluster_labels = None

    if 'income_segment' in df.columns:
        df_cluster = df.filter(
            pl.col('rent_to_income').is_not_null()
            & pl.col('commute_min_proxy').is_not_null()
        )

        if len(df_cluster) >= 10:
            rent_vals = df_cluster['rent_to_income'].to_numpy()
            commute_vals = df_cluster['commute_min_proxy'].to_numpy()
            rent_z = (rent_vals - rent_vals.mean()) / rent_vals.std()
            commute_z = (commute_vals - commute_vals.mean()) / commute_vals.std()
            x_cluster = np.column_stack([rent_z, commute_z])

            try:
                kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
                cluster_labels = kmeans.fit_predict(x_cluster)

                df_cluster = df_cluster.with_columns(
                    pl.Series('cluster', cluster_labels)
                )
                cluster_summary = df_cluster.group_by('cluster').agg([
                    pl.col('rent_to_income').mean().alias('mean_rent_burden'),
                    pl.col('commute_min_proxy').mean().alias('mean_commute'),
                    pl.col('rent_to_income').count().alias('n_zctas'),
                ]).sort('cluster')
                logger.info("K-Means clustering completed")
            except Exception as e:
                logger.warning(f"K-means clustering failed: {e}")

    return RQ2Results(
        interaction_model=interaction_model,
        rent_by_income=rent_by_income,
        commute_by_income=commute_by_income,
        anova_results=anova_results,
        cluster_summary=cluster_summary,
        cluster_labels=cluster_labels,
        df_with_segments=df,
    )


def _plot_income_boxplots(
    df: pl.DataFrame,
    fig_dir: Path,
    metro: str,
) -> None:
    """Generate boxplots of rent burden and commute by income segment."""
    income_groups = [g for g in ['Low', 'Medium', 'High']
                     if g in df['income_segment'].unique().to_list()]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

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
        axes[1].set_ylabel('Share with 45+ min Commute')
        axes[1].set_title('Long Commute Share by Income Segment')
    else:
        commute_data = [
            df.filter(pl.col('income_segment') == group)['commute_min_proxy'].to_numpy()
            for group in income_groups
        ]
        axes[1].set_ylabel('Commute Time (minutes)')
        axes[1].set_title('Commute Time by Income Segment')

    axes[1].boxplot(commute_data, labels=income_groups)
    axes[1].set_xlabel('Income Segment')
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(fig_dir / f"rq2_{metro.lower()}_boxplots.png", dpi=300, bbox_inches='tight')
    plt.close()


def _plot_race_boxplots(
    df: pl.DataFrame,
    fig_dir: Path,
    metro: str,
) -> None:
    """Generate boxplots of rent burden by majority race."""
    if 'majority_race' not in df.columns:
        return

    race_groups = sorted(df['majority_race'].unique().drop_nulls().to_list())
    race_data = []
    race_labels = []
    for group in race_groups:
        data = df.filter(pl.col('majority_race') == group)['rent_to_income'].drop_nulls().to_numpy()
        if len(data) > 0:
            race_data.append(data)
            race_labels.append(group)

    if len(race_labels) < 2:
        return

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.boxplot(race_data, labels=race_labels)
    ax.set_xlabel('Majority Race')
    ax.set_ylabel('Rent-to-Income Ratio')
    ax.set_title('Rent Burden by Majority Race')
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(fig_dir / f"rq2_{metro.lower()}_boxplots_race.png", dpi=300, bbox_inches='tight')
    plt.close()


def _plot_clusters(
    df: pl.DataFrame,
    cluster_labels: np.ndarray,
    fig_dir: Path,
    metro: str,
) -> None:
    """Generate scatter plot of K-means clusters."""
    fig, ax = plt.subplots(figsize=(10, 8))

    scatter = ax.scatter(
        df['commute_min_proxy'],
        df['rent_to_income'],
        c=cluster_labels,
        cmap='viridis',
        alpha=0.6,
        edgecolors='black',
        linewidths=0.5,
    )

    ax.set_xlabel('Commute Time (minutes)')
    ax.set_ylabel('Rent-to-Income Ratio')
    ax.set_title('K-Means Clusters: Affordability-Commute Zones')
    ax.grid(True, alpha=0.3)

    plt.colorbar(scatter, ax=ax, label='Cluster')
    plt.tight_layout()
    plt.savefig(fig_dir / f"rq2_{metro.lower()}_clusters.png", dpi=300, bbox_inches='tight')
    plt.close()


def report_rq2(
    results: RQ2Results,
    out_dir: Path,
    fig_dir: Path,
    metro: str,
) -> None:
    """Write RQ2 results to markdown and generate visualizations.

    Parameters
    ----------
    results : RQ2Results
        Output from analyze_rq2().
    out_dir : Path
        Markdown output directory.
    fig_dir : Path
        Figure output directory.
    metro : str
        Metro code for file naming.
    """
    md_path = out_dir / f"analysis_summary_{metro.lower()}.md"
    df = results.df_with_segments

    # Handle case where analysis was skipped
    if df is None:
        with open(md_path, 'a') as f:
            f.write("## RQ2: Equity Analysis\n\n")
            f.write("**Status:** Skipped - demographic columns not available.\n\n---\n\n")
        return

    # Interaction model coefficients
    if results.interaction_model:
        with open(md_path, 'a') as f:
            f.write("## RQ2: Equity Analysis\n\n")

        model = results.interaction_model
        coef_data = {
            'Variable': ['Intercept'] + model['feature_names'][1:],
            'Coefficient': [f"{val:.4f}" for val in model['params']],
            'Std Error': [f"{val:.4f}" for val in model['std_errors']],
            'p-value': [f"{val:.4f}" if val >= 0.0001 else '<0.0001'
                        for val in model['pvalues']],
        }
        save_markdown_table(coef_data, md_path, "RQ2: Interaction Model Coefficients")

    # Group statistics
    if results.rent_by_income is not None:
        with open(md_path, 'a') as f:
            f.write("### Group Comparisons\n\n")

        ri = results.rent_by_income
        rent_stats = {
            'Income Segment': ri['income_segment'].to_list(),
            'Mean Rent Burden': [f"{val:.3f}" for val in ri['mean_rent_burden'].to_list()],
            'Std Dev': [f"{val:.3f}" for val in ri['std_rent_burden'].to_list()],
            'N': [str(val) for val in ri['n'].to_list()],
        }
        save_markdown_table(rent_stats, md_path, "Rent Burden by Income Segment")

    if results.commute_by_income is not None:
        ci = results.commute_by_income
        commute_stats = {
            'Income Segment': ci['income_segment'].to_list(),
            'Mean Long45 Share': [f"{val:.3f}" for val in ci['mean_long45'].to_list()],
            'Std Dev': [f"{val:.3f}" for val in ci['std_long45'].to_list()],
            'N': [str(val) for val in ci['n'].to_list()],
        }
        save_markdown_table(commute_stats, md_path, "Long Commute Share by Income Segment")

    # Cluster summary
    if results.cluster_summary is not None:
        cs = results.cluster_summary
        cluster_stats = {
            'Cluster': [f"Cluster {i}" for i in cs['cluster'].to_list()],
            'Mean Rent Burden': [f"{val:.3f}" for val in cs['mean_rent_burden'].to_list()],
            'Mean Commute (min)': [f"{val:.1f}" for val in cs['mean_commute'].to_list()],
            'N ZCTAs': [str(val) for val in cs['n_zctas'].to_list()],
        }
        save_markdown_table(cluster_stats, md_path,
                            "K-Means Clusters (Affordability/Commute Zones)")

    # Plots
    if 'income_segment' in df.columns:
        _plot_income_boxplots(df, fig_dir, metro)
        _plot_race_boxplots(df, fig_dir, metro)

    if results.cluster_labels is not None and results.cluster_summary is not None:
        df_cluster = df.filter(
            pl.col('rent_to_income').is_not_null()
            & pl.col('commute_min_proxy').is_not_null()
        )
        _plot_clusters(df_cluster, results.cluster_labels, fig_dir, metro)

    # ANOVA results table
    anova_vars = []
    anova_fstats = []
    anova_pvals = []
    anova_sig = []

    # Map target_col to human-readable names
    anova_names = {
        'rent_to_income': 'Rent Burden',
        'long45_share': 'Long Commute Share',
        'stops_per_km2': 'Transit Density',
    }

    for ar in results.anova_results:
        if ar.f_stat is not None:
            name = anova_names.get(ar.variable, f"{ar.variable} by Race")
            anova_vars.append(name)
            anova_fstats.append(f"{ar.f_stat:.3f}")
            anova_pvals.append(f"{ar.p_value:.4f}" if ar.p_value >= 0.0001 else '<0.0001')
            anova_sig.append('Yes' if ar.significant else 'No')

    if anova_vars:
        anova_data = {
            'Variable': anova_vars,
            'F-statistic': anova_fstats,
            'p-value': anova_pvals,
            'Significant (a=0.05)': anova_sig,
        }
        save_markdown_table(anova_data, md_path,
                            "ANOVA: Group Comparisons Across Income Segments")

    # Interpretation
    with open(md_path, 'a') as f:
        f.write("#### Interpretation\n\n")

        if results.interaction_model:
            pvals = results.interaction_model['pvalues']
            interaction_pval = pvals[3] if len(pvals) > 3 else 1.0
            if interaction_pval < 0.05:
                f.write("**Interaction Effect:** The interaction between commute time "
                        "and low-income status is statistically significant (p < 0.05), "
                        "suggesting inequity in the affordability-commute trade-off.\n\n")
            else:
                f.write("**Interaction Effect:** The interaction is not statistically "
                        f"significant (p = {interaction_pval:.4f}).\n\n")

        # ANOVA interpretation for rent burden
        rent_anova = next((a for a in results.anova_results
                           if a.variable == 'rent_to_income' and a.f_stat is not None), None)
        if rent_anova:
            if rent_anova.significant:
                f.write(f"**Income Disparities:** ANOVA confirms significant differences "
                        f"in rent burden (F={rent_anova.f_stat:.2f}, "
                        f"p={rent_anova.p_value:.4f}).\n\n")
            else:
                f.write(f"**Income Disparities:** No significant differences "
                        f"(F={rent_anova.f_stat:.2f}, p={rent_anova.p_value:.4f}).\n\n")

        f.write("**K-Means Clustering:** ZCTAs grouped into four affordability-commute "
                "zones based on rent burden and commute time patterns.\n\n")

        f.write(f"**Figures:** `rq2_{metro.lower()}_boxplots.png`, ")
        if 'majority_race' in df.columns:
            f.write(f"`rq2_{metro.lower()}_boxplots_race.png`, ")
        f.write(f"`rq2_{metro.lower()}_clusters.png`\n\n")
        f.write("---\n\n")

    logger.info("RQ2 results saved")


def run_rq2(df: pl.DataFrame, out_dir: Path, fig_dir: Path, metro: str) -> None:
    """RQ2: Equity analysis (full pipeline).

    Delegates to analyze_rq2() and report_rq2() for separation of concerns.

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
    results = analyze_rq2(df)
    report_rq2(results, out_dir, fig_dir, metro)
