"""RQ4: ZORI Rent Dynamics — did COVID reprice the commute gradient?

Spec A family (design doc section 4): per-metro two-way fixed-effects
estimation of the 2020 structural break in the pre-COVID commute gradient
on the monthly ZORI panel.

Model:
    log(zori_it) = a_i + g_t
                   + sum_x [ B1_x (x_i * Post1_t) + B2_x (x_i * Post2_t) ]
                   + e_it

    Post1_t = 1[2020-03 <= t <= 2021-12]   (disruption phase)
    Post2_t = 1[t >= 2022-01]              (partial return-to-office phase)

`a_i` are ZCTA fixed effects (absorb every time-invariant amenity and the
main effects of the x's); `g_t` are sample-month fixed effects (absorb
metro-wide shocks, seasonality, and the Post main effects). Only the
interactions are identified — which is exactly the question.

Headline interaction set — measured pre-treatment (design section 4):

- ``commute_min_proxy_2019`` (ACS 5-year 2015-2019, ZCTA altitude);
- ``distance_to_cbd_km`` (pure geometry, vintage-free);
- log ``job_accessibility_2019`` (the 2019 rows of the LODES panel).

The 2021-vintage variant (35-column ``commute_min_proxy`` + LODES-2021
accessibility) is demoted to a "measured-gradient" sensitivity because both
regressors partially embed the COVID response.

Sample: all (i, t) cells minus the endpoint trim (``ENDPOINT_TRIM_MONTHS``
final months of the pull, which revise the most). The transition-window
drop (2020-03..05 excluded) is CO-headline, not an afterthought: it covers
both the 2020-03-vs-04 break ambiguity and the smoothed index spreading a
March-2020 shock over ~3 index months. The top-level sample counts on
``RQ4Results`` (``n_obs``, ``n_pre_months``, ``n_post_months``) describe the
strictest headline sample — endpoint trim AND transition drop applied.

Inference: cluster-robust by ZCTA via the within-FE estimator
(``panel_fe.within_fe``, conservative dof convention), p-values from the t
distribution with G-1 dof (G = clusters). Webb wild cluster bootstrap
p-values supplement the conventional ones twice over (design section 4,
estimator layer 3): (a) ZIP3 coarse-cluster spatial robustness, always;
(b) ZCTA-level headline p-values when the metro is under-identified (fewer
than ``UNDER_IDENTIFIED_MIN`` ZCTAs observed on both sides of the break).

No I/O in this module's ``analyze_rq4`` — pure computation on the frames
the caller loaded (``load_panel_data`` + the 35-column cross-section).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import numpy as np
import polars as pl
from scipy import stats

from .panel_fe import FEResult, wald_joint, wild_cluster_boot_p, within_fe
from .results import RQ4Results

logger = logging.getLogger(__name__)

#: Final months of each pull dropped from estimation (they revise the most).
ENDPOINT_TRIM_MONTHS = 1

#: Two-phase break (design section 4, Spec A). Month-end dates.
POST1_START = date(2020, 3, 31)
POST1_END = date(2021, 12, 31)
POST2_START = date(2022, 1, 31)

#: Co-headline transition-window drop: 2020-03..2020-05 excluded.
TRANSITION_WINDOW = (date(2020, 3, 31), date(2020, 5, 31))

#: Balanced-subpanel robustness: ZCTAs in-sample by this month.
BALANCED_CUTOFF = date(2019, 1, 31)

#: Entrant-composition table: entrants are ZCTAs first observed after this.
ENTRANT_CUTOFF = date(2019, 12, 31)

#: Metros with fewer identifying ZCTAs than this are flagged and get
#: ZCTA-level wild-bootstrap p-values beside the conventional ones.
UNDER_IDENTIFIED_MIN = 20

#: Headline (pre-COVID vintage) gradient regressors, in report order.
GRADIENT_X_2019 = (
    "commute_min_proxy_2019",
    "distance_to_cbd_km",
    "log_job_accessibility_2019",
)

#: Measured-gradient (2021-vintage) sensitivity regressors.
GRADIENT_X_2021 = (
    "commute_min_proxy",
    "distance_to_cbd_km",
    "log_job_accessibility_2021",
)

#: Deterministic seed for every bootstrap draw in this module.
_BOOT_SEED = 20260717


def _estimation_frame(
    cross_df: pl.DataFrame,
    zori_panel: pl.DataFrame,
    lodes_panel: pl.DataFrame,
    acs2019_df: pl.DataFrame,
) -> pl.DataFrame:
    """Merge the four inputs into one long estimation frame.

    Inner joins on ``ZCTA5CE`` attach both gradient vintages to every
    (ZCTA, month) cell: the pre-COVID set (2019 commute proxy, geometry
    distance, log LODES-2019 accessibility) and the 2021-vintage set
    (35-column proxy, log LODES-2021 accessibility from the cross-section).
    Adds ``period_date`` (parsed month-end) and ``log_zori``.
    """
    lodes_2019 = lodes_panel.filter(pl.col("year") == 2019).select(
        "ZCTA5CE",
        pl.col("job_accessibility").log().alias("log_job_accessibility_2019"),
    )
    cross = cross_df.select(
        "ZCTA5CE",
        "distance_to_cbd_km",
        "commute_min_proxy",
        pl.col("job_accessibility").log().alias("log_job_accessibility_2021"),
    )
    return (
        zori_panel.with_columns(
            pl.col("period").str.to_date("%Y-%m-%d").alias("period_date"),
            pl.col("zori").log().alias("log_zori"),
        )
        .join(
            acs2019_df.select("ZCTA5CE", "commute_min_proxy_2019"),
            on="ZCTA5CE",
            how="inner",
        )
        .join(cross, on="ZCTA5CE", how="inner")
        .join(lodes_2019, on="ZCTA5CE", how="inner")
        .sort("ZCTA5CE", "period")
    )


def _endpoint_trim(frame: pl.DataFrame) -> pl.DataFrame:
    """Drop the final ``ENDPOINT_TRIM_MONTHS`` months of the pull."""
    periods = sorted(frame["period"].unique().to_list())
    keep = periods[: len(periods) - ENDPOINT_TRIM_MONTHS]
    return frame.filter(pl.col("period").is_in(keep))


def _drop_transition(frame: pl.DataFrame) -> pl.DataFrame:
    """Exclude the transition window (co-headline sample)."""
    lo, hi = TRANSITION_WINDOW
    return frame.filter(
        ~((pl.col("period_date") >= lo) & (pl.col("period_date") <= hi))
    )


def _phase_masks(frame: pl.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """(Post1, Post2) indicator arrays for the frame's rows."""
    dates = frame["period_date"].to_list()
    post1 = np.array(
        [POST1_START <= d <= POST1_END for d in dates], dtype=float
    )
    post2 = np.array([d >= POST2_START for d in dates], dtype=float)
    return post1, post2


def _design(
    frame: pl.DataFrame,
    x_vars: tuple[str, ...],
    masks: list[np.ndarray],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(y, X, unit_codes, time_ids, zcta_labels) for the interaction model.

    ``X`` columns are ordered mask-major: for masks ``[m1, m2]`` and K vars,
    columns 0..K-1 are ``x*m1`` and columns K..2K-1 are ``x*m2``.
    """
    y = frame["log_zori"].to_numpy()
    cols = [
        frame[var].to_numpy() * mask for mask in masks for var in x_vars
    ]
    X = np.column_stack(cols)
    zctas = np.asarray(frame["ZCTA5CE"].to_list())
    _, unit_codes = np.unique(zctas, return_inverse=True)
    times = np.asarray(frame["period"].to_list())
    return y, X, unit_codes, times, zctas


def _coef_block(
    fe: FEResult, x_vars: tuple[str, ...], phases: tuple[str, ...]
) -> dict[str, dict[str, float]]:
    """Per-variable coefficient dicts with conservative t(G-1) p-values."""
    dof = fe.n_units - 1  # clusters == units for the ZCTA-clustered fits
    out: dict[str, dict[str, float]] = {var: {} for var in x_vars}
    for p_idx, phase in enumerate(phases):
        for v_idx, var in enumerate(x_vars):
            j = p_idx * len(x_vars) + v_idx
            coef = float(fe.params[j])
            se = float(fe.bse[j])
            pval = float(2.0 * stats.t.sf(abs(coef / se), df=dof))
            out[var][f"{phase}_coef"] = coef
            out[var][f"{phase}_se"] = se
            out[var][f"{phase}_pvalue"] = pval
    return out


def _fit_two_phase(
    frame: pl.DataFrame,
    x_vars: tuple[str, ...],
    x_vintage: str,
    sample: str,
) -> tuple[dict[str, Any], FEResult]:
    """Joint two-phase interaction model on ``frame``.

    Returns the report-ready model dict and the raw ``FEResult`` (the caller
    needs its covariance for the phase Wald tests).
    """
    post1, post2 = _phase_masks(frame)
    y, X, units, times, _ = _design(frame, x_vars, [post1, post2])
    fe = within_fe(y, X, units, times, cluster_ids=units)
    model = {
        "x_vars": list(x_vars),
        "x_vintage": x_vintage,
        "sample": sample,
        "coefs": _coef_block(fe, x_vars, ("post1", "post2")),
        "n_obs": fe.n_obs,
        "n_units": fe.n_units,
        "n_clusters": fe.n_units,
        "dof_note": fe.dof_note,
    }
    return model, fe


def _fit_single(
    frame: pl.DataFrame, var: str, x_vintage: str
) -> dict[str, Any]:
    """Single-interaction two-phase model (sign robustness), flat dict."""
    model, _ = _fit_two_phase(frame, (var,), x_vintage, "full")
    flat: dict[str, Any] = dict(model["coefs"][var])
    flat.update(
        x_vintage=x_vintage,
        n_obs=model["n_obs"],
        n_units=model["n_units"],
        dof_note=model["dof_note"],
    )
    return flat


def _fit_pooled(
    frame: pl.DataFrame, x_vars: tuple[str, ...], x_vintage: str
) -> tuple[dict[str, Any], FEResult]:
    """Single-Post pooled summary (averages over a non-monotone path)."""
    post1, post2 = _phase_masks(frame)
    pooled_mask = np.clip(post1 + post2, 0.0, 1.0)
    y, X, units, times, _ = _design(frame, x_vars, [pooled_mask])
    fe = within_fe(y, X, units, times, cluster_ids=units)
    model = {
        "x_vars": list(x_vars),
        "x_vintage": x_vintage,
        "coefs": _coef_block(fe, x_vars, ("post",)),
        "n_obs": fe.n_obs,
        "n_units": fe.n_units,
        "dof_note": fe.dof_note,
        "note": (
            "single-Post summary; averages over a non-monotone "
            "disruption-then-partial-reversal path"
        ),
    }
    return model, fe


def _bootstrap_block(
    frame: pl.DataFrame,
    x_vars: tuple[str, ...],
    cluster_labels: np.ndarray,
) -> dict[str, Any]:
    """Webb wild-cluster bootstrap p-values per (variable, phase).

    ``cluster_labels`` must nest ZCTAs (ZCTA-level or ZIP3-prefix labels).
    Returns ``{"note": ...}`` instead of raising when the metro has fewer
    than 3 clusters at this level.
    """
    n_clusters = len(set(cluster_labels.tolist()))
    if n_clusters < 3:
        return {
            "note": f"skipped: {n_clusters} clusters (< 3) at this level"
        }
    post1, post2 = _phase_masks(frame)
    y, X, units, times, _ = _design(frame, x_vars, [post1, post2])
    out: dict[str, Any] = {}
    for v_idx, var in enumerate(x_vars):
        out[var] = {
            phase: wild_cluster_boot_p(
                y,
                X,
                units,
                times,
                cluster_labels,
                coef_idx=p_idx * len(x_vars) + v_idx,
                seed=_BOOT_SEED + p_idx * len(x_vars) + v_idx,
            )
            for p_idx, phase in enumerate(("post1", "post2"))
        }
    return out


def _coverage(
    cross_df: pl.DataFrame, zori_panel: pl.DataFrame
) -> dict[str, Any]:
    """Covered-ZCTA shares of the metro universe, overall and per year."""
    n_universe = cross_df["ZCTA5CE"].n_unique()
    with_year = zori_panel.with_columns(
        pl.col("period").str.to_date("%Y-%m-%d").dt.year().alias("year")
    )
    by_year = (
        with_year.group_by("year")
        .agg(pl.col("ZCTA5CE").n_unique().alias("n_covered"))
        .sort("year")
    )
    return {
        "n_universe": int(n_universe),
        "n_covered": int(zori_panel["ZCTA5CE"].n_unique()),
        "share_covered": zori_panel["ZCTA5CE"].n_unique() / n_universe,
        "share_by_year": {
            int(y): n / n_universe
            for y, n in zip(by_year["year"], by_year["n_covered"])
        },
    }


def _first_seen(zori_panel: pl.DataFrame) -> pl.DataFrame:
    """First observed month-end per ZCTA (``entry`` date column)."""
    return zori_panel.group_by("ZCTA5CE").agg(
        pl.col("period").str.to_date("%Y-%m-%d").min().alias("entry")
    )


def _entrant_composition(
    frame: pl.DataFrame, first_seen: pl.DataFrame
) -> pl.DataFrame:
    """Mean of each gradient x: post-ENTRANT_CUTOFF entrants vs incumbents.

    Signs the entry-selection direction (design section 4 diagnostics): if
    entrants are systematically high-x (peripheral markets thickening into
    ZORI coverage), the identifying subsample tilts toward incumbents.
    """
    attrs = frame.unique(subset="ZCTA5CE", keep="first", maintain_order=True)
    attrs = attrs.join(first_seen, on="ZCTA5CE", how="inner").with_columns(
        (pl.col("entry") > ENTRANT_CUTOFF).alias("is_entrant")
    )
    entrants = attrs.filter(pl.col("is_entrant"))
    incumbents = attrs.filter(~pl.col("is_entrant"))
    rows = [
        {
            "variable": var,
            "incumbent_mean": (
                float(incumbents[var].mean()) if incumbents.height else None
            ),
            "entrant_mean": (
                float(entrants[var].mean()) if entrants.height else None
            ),
            "n_incumbents": incumbents.height,
            "n_entrants": entrants.height,
        }
        for var in GRADIENT_X_2019
    ]
    return pl.DataFrame(rows)


def analyze_rq4(
    cross_df: pl.DataFrame,
    zori_panel: pl.DataFrame,
    lodes_panel: pl.DataFrame,
    acs2019_df: pl.DataFrame,
) -> RQ4Results:
    """Spec-A family of the RQ4 analysis (pure computation, no I/O).

    Parameters
    ----------
    cross_df : pl.DataFrame
        The metro's 35-column cross-section (needs ``ZCTA5CE``,
        ``distance_to_cbd_km``, ``commute_min_proxy``,
        ``job_accessibility``).
    zori_panel : pl.DataFrame
        Long ZORI panel: ``ZCTA5CE``, ``period`` (ISO month-end str),
        ``zori``.
    lodes_panel : pl.DataFrame
        Annual accessibility panel: ``ZCTA5CE``, ``year``, ``job_count``,
        ``job_accessibility``.
    acs2019_df : pl.DataFrame
        Pre-COVID commute vintage: ``ZCTA5CE``, ``commute_min_proxy_2019``,
        ``ttw_total_2019``.

    Returns
    -------
    RQ4Results
        Spec-A fields populated; the Task-18 fields (event study, Specs
        C/C-med/D) are structurally empty until that task lands.
    """
    frame_all = _estimation_frame(cross_df, zori_panel, lodes_panel, acs2019_df)
    frame = _endpoint_trim(frame_all)
    frame_headline = _drop_transition(frame)

    # --- headline: two-phase joint on the pre-COVID vintage -----------------
    # The transition-window drop is CO-headline (design section 4): the full
    # trimmed sample carries the top-level dict, the transition-dropped
    # variant sits beside it under "transition_drop" with equal standing.
    joint, joint_fe = _fit_two_phase(frame, GRADIENT_X_2019, "2019", "full")
    joint_drop, _ = _fit_two_phase(
        frame_headline, GRADIENT_X_2019, "2019", "transition_dropped"
    )
    joint["transition_drop"] = joint_drop

    singles = {
        var: _fit_single(frame, var, "2019") for var in GRADIENT_X_2019
    }
    pooled, pooled_fe = _fit_pooled(frame, GRADIENT_X_2019, "2019")

    k = len(GRADIENT_X_2019)
    wald_break: dict[str, Any] = {}
    for key, fe_res, idx in (
        ("phase1", joint_fe, list(range(k))),
        ("phase2", joint_fe, list(range(k, 2 * k))),
        ("pooled", pooled_fe, list(range(k))),
    ):
        stat, pval = wald_joint(fe_res, idx)
        wald_break[key] = {"stat": stat, "pvalue": pval, "df": len(idx)}

    # --- identification accounting ------------------------------------------
    pre_zctas = set(
        frame.filter(pl.col("period_date") < POST1_START)["ZCTA5CE"].to_list()
    )
    post_zctas = set(
        frame.filter(pl.col("period_date") >= POST1_START)["ZCTA5CE"].to_list()
    )
    n_identifying = len(pre_zctas & post_zctas)
    flags: list[str] = []
    if n_identifying < UNDER_IDENTIFIED_MIN:
        flags.append("under_identified")
        logger.warning(
            "under-identified metro: %d identifying ZCTAs (< %d); "
            "reporting ZCTA-level bootstrap p-values",
            n_identifying,
            UNDER_IDENTIFIED_MIN,
        )

    # --- bootstrap p-values (design section 4, estimator layer 3) -----------
    # "zip3" key: coarse-cluster spatial robustness, always computed.
    # Regressor-name keys: ZCTA-level headline bootstrap, present only for
    # under-identified metros (beside the conventional p-values).
    zctas = np.asarray(frame["ZCTA5CE"].to_list())
    zip3_labels = np.asarray([z[:3] for z in zctas])
    bootstrap_pvalues: dict[str, Any] = {
        "zip3": _bootstrap_block(frame, GRADIENT_X_2019, zip3_labels)
    }
    if "under_identified" in flags:
        bootstrap_pvalues.update(
            _bootstrap_block(frame, GRADIENT_X_2019, zctas)
        )

    # --- robustness suite ----------------------------------------------------
    vintage2021, _ = _fit_two_phase(frame, GRADIENT_X_2021, "2021", "full")
    vintage2021_robustness = {
        "vintage2021": vintage2021,
        "note": (
            "measured-gradient sensitivity: 2021-vintage regressors "
            "(ACS 2017-2021 proxy, LODES-2021 accessibility) partially "
            "embed the COVID response and are never the headline"
        ),
    }

    first_seen = _first_seen(zori_panel)
    balanced_zctas = first_seen.filter(pl.col("entry") <= BALANCED_CUTOFF)[
        "ZCTA5CE"
    ].to_list()
    balanced_frame = frame.filter(pl.col("ZCTA5CE").is_in(balanced_zctas))
    balanced_joint, _ = _fit_two_phase(
        balanced_frame, GRADIENT_X_2019, "2019", "balanced"
    )
    balanced_robustness = {
        "joint": balanced_joint,
        "n_zctas": len(balanced_zctas),
        "note": f"ZCTAs in-sample by {BALANCED_CUTOFF.isoformat()}",
    }

    # --- diagnostics + sample accounting (strictest headline sample) --------
    n_pre_months = frame_headline.filter(
        pl.col("period_date") < POST1_START
    )["period"].n_unique()
    n_post_months = frame_headline.filter(
        pl.col("period_date") >= POST1_START
    )["period"].n_unique()

    logger.info(
        "RQ4 Spec A: %d obs, %d ZCTAs (%d identifying), %d pre / %d post "
        "months after trims",
        frame_headline.height,
        frame_headline["ZCTA5CE"].n_unique(),
        n_identifying,
        n_pre_months,
        n_post_months,
    )

    empty = pl.DataFrame()
    return RQ4Results(
        gradient_model_joint=joint,
        gradient_models_single=singles,
        gradient_model_pooled=pooled,
        wald_break=wald_break,
        bootstrap_pvalues=bootstrap_pvalues,
        event_study=empty,  # Task 18
        access_model={},  # Task 18
        mediation={},  # Task 18
        chase_model_lagged={},  # Task 18
        chase_model_lead={},  # Task 18
        chase_model_contemp={},  # Task 18
        long_difference={},  # Task 18
        vintage2021_robustness=vintage2021_robustness,
        n_obs=frame_headline.height,
        n_zctas=frame_headline["ZCTA5CE"].n_unique(),
        n_identifying=n_identifying,
        n_pre_months=n_pre_months,
        n_post_months=n_post_months,
        coverage=_coverage(cross_df, zori_panel),
        balanced_robustness=balanced_robustness,
        entrant_composition=_entrant_composition(frame_all, first_seen),
        flags=flags,
    )
