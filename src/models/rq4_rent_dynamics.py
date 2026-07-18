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

Beyond Spec A, the module runs (design section 4):

- **Spec B — event study**: interactions of the gradient x's with event-time
  bins defined relative to 2020-03, NOT calendar years (calendar-year bins
  would put pre-break 2020-01/02 into the treated bin). Base bin
  2019-03..2020-02; 12-month pre bins counting back (2015-01/02 folded into
  the earliest); 6-month post bins through 2022-02, 12-month after. The
  ``event_study`` frame carries per-bin identifying ZCTA counts.
- **Spec C — time-varying access**: annual LODES accessibility merged by
  calendar year, window truncated at the last LODES year (no carry-forward
  inside estimation — carried-forward values would fabricate zero within-
  variation and attenuate theta). Robustness: 2-year-averaged access and
  2020/2021 LODES years dropped.
- **Spec C-med — mediation decomposition**: contemporaneous access added to
  Spec A is a mediator (itself a COVID outcome), not a control; reported as
  the share of Post1 repricing absorbed, labeled mediation — never
  "robustness".
- **Spec D — predictive association**: annual mean log rent (>=
  ``MIN_MONTHS_PER_YEAR`` observed months per (i, y) cell) on lagged log
  access, with a lead-term falsification (a significant lead means feedback,
  not chasing), a contemporaneous variant, and long differences
  (2015->2019, 2019->2023). Written up as association, never causal.

No I/O in this module's ``analyze_rq4`` — pure computation on the frames
the caller loaded (``load_panel_data`` + the 35-column cross-section).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import numpy as np
import polars as pl
import statsmodels.api as sm
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

#: Spec D annual collapse: minimum observed months per (ZCTA, year) cell —
#: thinner cells would dominate the annual mean (design section 4, Spec D).
MIN_MONTHS_PER_YEAR = 6

#: Spec D long-difference windows (start year, end year).
LONG_DIFF_WINDOWS = ((2015, 2019), (2019, 2023))

#: Event-study bin grammar (design section 4, Spec B). Month indexes
#: (year * 12 + month - 1) of the base-bin start (2019-03), the break
#: (2020-03), and the 6-month-to-12-month post-bin switch (2022-03).
_BASE_START_M = 2019 * 12 + 2
_BREAK_M = 2020 * 12 + 2
_POST_WIDE_M = 2022 * 12 + 2

#: Earliest pre bin (2015-03..2016-02); 2015-01/02 fold into it because the
#: ZORI panel starts 2015-01 (design section 4, Spec B).
_EARLIEST_PRE_ORDER = -4

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


# ---------------------------------------------------------------------------
# Spec B — event study on event-time bins relative to 2020-03
# ---------------------------------------------------------------------------


def event_time_bin(d: date) -> tuple[int, str]:
    """Assign a month-end date to its event-time bin (design section 4, Spec B).

    Bins are relative to the 2020-03 break, NOT calendar years (calendar-year
    bins would put pre-break 2020-01/02 into the treated "2020" bin,
    mechanically attenuating the first post coefficient). Grammar:

    - base bin (order 0): 2019-03 .. 2020-02;
    - pre bins (order -1, -2, ...): 12-month bins counting back from the
      base; 2015-01/02 fold into the earliest bin (order -4);
    - post bins (order 1..4): 6-month bins over 2020-03 .. 2022-02;
    - post bins (order 5, 6, ...): 12-month bins from 2022-03 onward.

    Returns
    -------
    tuple[int, str]
        (bin order, bin label) — e.g. ``(0, "base")``, ``(-1, "pre1")``,
        ``(1, "post1")``.
    """
    m = d.year * 12 + d.month - 1
    if m >= _POST_WIDE_M:
        order = 5 + (m - _POST_WIDE_M) // 12
    elif m >= _BREAK_M:
        order = (m - _BREAK_M) // 6 + 1
    elif m >= _BASE_START_M:
        return 0, "base"
    else:
        order = -((_BASE_START_M - 1 - m) // 12 + 1)
        order = max(order, _EARLIEST_PRE_ORDER)  # fold 2015-01/02
    label = f"post{order}" if order > 0 else f"pre{-order}"
    return order, label


def _event_study(frame: pl.DataFrame) -> pl.DataFrame:
    """Spec B: gradient x's interacted with event-time bins, per-bin counts.

    One joint two-way FE fit with every non-base (bin x variable)
    interaction; the base bin appears in the output as the zero reference
    row. ``n_identifying`` per bin counts distinct ZCTAs observed in that
    bin (the design's Denver example: earliest bins resting on 10 ZIPs).
    """
    orders = np.array(
        [event_time_bin(d)[0] for d in frame["period_date"].to_list()]
    )
    bin_orders = sorted(set(orders.tolist()))
    nonbase = [b for b in bin_orders if b != 0]

    masks = [(orders == b).astype(float) for b in nonbase]
    y, X, units, times, zctas = _design(frame, GRADIENT_X_2019, masks)
    fe = within_fe(y, X, units, times, cluster_ids=units)
    tcrit = float(stats.t.ppf(0.975, fe.n_units - 1))

    n_by_bin = {
        b: len(set(zctas[orders == b].tolist())) for b in bin_orders
    }

    def _label(order: int) -> str:
        return "base" if order == 0 else (
            f"post{order}" if order > 0 else f"pre{-order}"
        )

    rows: list[dict[str, Any]] = []
    for b in bin_orders:
        for v_idx, var in enumerate(GRADIENT_X_2019):
            if b == 0:
                coef = se = 0.0  # omitted reference bin
            else:
                j = nonbase.index(b) * len(GRADIENT_X_2019) + v_idx
                coef, se = float(fe.params[j]), float(fe.bse[j])
            rows.append({
                "variable": var,
                "bin": _label(b),
                "bin_order": b,
                "coef": coef,
                "se": se,
                "ci_lo": coef - tcrit * se,
                "ci_hi": coef + tcrit * se,
                "n_identifying": n_by_bin[b],
            })
    return pl.DataFrame(rows)


# ---------------------------------------------------------------------------
# Spec C — time-varying annual accessibility (+ C-med mediation)
# ---------------------------------------------------------------------------


def _access_frame(
    frame: pl.DataFrame, lodes_panel: pl.DataFrame
) -> pl.DataFrame:
    """Merge annual log accessibility into the monthly frame by calendar year.

    The window is truncated at the last LODES year (inner join by year makes
    carry-forward impossible: months beyond the last LODES year have no
    access row to merge — design section 4, Spec C).
    """
    last_year = int(lodes_panel["year"].max())
    return (
        frame.filter(pl.col("period_date") <= date(last_year, 12, 31))
        .with_columns(pl.col("period_date").dt.year().alias("year"))
        .join(
            lodes_panel.select(
                "ZCTA5CE",
                "year",
                pl.col("job_accessibility").log().alias("log_access_year"),
            ),
            on=["ZCTA5CE", "year"],
            how="inner",
        )
        .sort("ZCTA5CE", "period")
    )


def _fit_theta(frame_c: pl.DataFrame, access_col: str, note: str) -> dict[str, Any]:
    """Two-way FE fit of log rent on one time-varying access column."""
    y = frame_c["log_zori"].to_numpy()
    X = frame_c[access_col].to_numpy()[:, None]
    zctas = np.asarray(frame_c["ZCTA5CE"].to_list())
    _, units = np.unique(zctas, return_inverse=True)
    times = np.asarray(frame_c["period"].to_list())
    fe = within_fe(y, X, units, times, cluster_ids=units)
    dof = fe.n_units - 1
    theta, se = float(fe.params[0]), float(fe.bse[0])
    return {
        "theta": theta,
        "se": se,
        "pvalue": float(2.0 * stats.t.sf(abs(theta / se), df=dof)),
        "n_obs": fe.n_obs,
        "n_units": fe.n_units,
        "n_clusters": fe.n_units,
        "max_period": str(frame_c["period"].max()),
        "years": sorted(frame_c["year"].unique().to_list()),
        "dof_note": fe.dof_note,
        "note": note,
    }


def _access_model(
    frame_c: pl.DataFrame, lodes_panel: pl.DataFrame
) -> dict[str, Any]:
    """Spec C: theta on contemporaneous annual access, with robustness.

    Robustness (design section 4, Spec C — LODES measurement caveat acted
    on): (a) 2-year-averaged access; (b) 2020/2021 LODES years dropped
    (block-noise infusion and geocoding reassignments are worst there).
    """
    last_year = int(lodes_panel["year"].max())
    headline = _fit_theta(
        frame_c,
        "log_access_year",
        (
            f"annual access merged by calendar year; window ends "
            f"{last_year}-12 (last LODES year) — no carry-forward inside "
            "estimation"
        ),
    )

    lp = lodes_panel.select("ZCTA5CE", "year", "job_accessibility")
    prev = lp.rename({"job_accessibility": "access_prev"}).with_columns(
        (pl.col("year") + 1).alias("year")
    )
    avg2 = (
        lp.join(prev, on=["ZCTA5CE", "year"], how="left")
        .with_columns(
            pl.when(pl.col("access_prev").is_null())
            .then(pl.col("job_accessibility"))
            .otherwise(
                (pl.col("job_accessibility") + pl.col("access_prev")) / 2.0
            )
            .log()
            .alias("log_access_avg2")
        )
        .select("ZCTA5CE", "year", "log_access_avg2")
    )
    frame_avg2 = frame_c.join(avg2, on=["ZCTA5CE", "year"], how="inner")
    frame_no_covid = frame_c.filter(~pl.col("year").is_in([2020, 2021]))

    headline["robustness"] = {
        "avg2yr": _fit_theta(
            frame_avg2,
            "log_access_avg2",
            "2-year-averaged access (smooths LODES block-noise infusion)",
        ),
        "drop_covid_years": _fit_theta(
            frame_no_covid,
            "log_access_year",
            "2020/2021 LODES years dropped (worst measurement offenders)",
        ),
    }
    return headline


def _mediation(frame_c: pl.DataFrame) -> dict[str, Any]:
    """Spec C-med: share of Post1 repricing absorbed by contemporaneous access.

    Re-estimates the Spec A joint model on the Spec C sample (so the
    comparison is like-for-like), then adds contemporaneous log access as a
    mediator. The mediator is itself a COVID outcome, so this is a mediation
    decomposition — "what share of the repricing runs through contemporaneous
    job relocation?" — never a robustness check on the break coefficients.
    """
    post1, post2 = _phase_masks(frame_c)
    y, X_base, units, times, _ = _design(
        frame_c, GRADIENT_X_2019, [post1, post2]
    )
    fe_base = within_fe(y, X_base, units, times, cluster_ids=units)

    mediator = frame_c["log_access_year"].to_numpy()
    X_med = np.column_stack([X_base, mediator])
    fe_med = within_fe(y, X_med, units, times, cluster_ids=units)

    k = len(GRADIENT_X_2019)
    post1_base = {
        var: float(fe_base.params[i]) for i, var in enumerate(GRADIENT_X_2019)
    }
    post1_med = {
        var: float(fe_med.params[i]) for i, var in enumerate(GRADIENT_X_2019)
    }
    share_by_x = {
        var: (
            1.0 - post1_med[var] / post1_base[var]
            if abs(post1_base[var]) > 1e-12
            else None
        )
        for var in GRADIENT_X_2019
    }

    dof = fe_med.n_units - 1
    theta_m, se_m = float(fe_med.params[2 * k]), float(fe_med.bse[2 * k])
    return {
        "label": "mediation decomposition (Spec C-med)",
        # headline scalar: the geometry regressor — vintage-free, so its
        # Post1 coefficient is the cleanest repricing measure to decompose
        "headline_variable": "distance_to_cbd_km",
        "share_mediated": share_by_x["distance_to_cbd_km"],
        "share_by_x": share_by_x,
        "post1_base": post1_base,
        "post1_mediated": post1_med,
        "mediator": {
            "coef": theta_m,
            "se": se_m,
            "pvalue": float(2.0 * stats.t.sf(abs(theta_m / se_m), df=dof)),
        },
        "n_obs": fe_med.n_obs,
        "max_period": str(frame_c["period"].max()),
        "note": (
            "share of Post1 repricing absorbed by contemporaneous access; "
            "the mediator is itself a COVID outcome, so the standard "
            "selection-into-mediator caveat applies"
        ),
    }


# ---------------------------------------------------------------------------
# Spec D — annual predictive association (rents and job growth)
# ---------------------------------------------------------------------------


def collapse_annual(frame: pl.DataFrame) -> pl.DataFrame:
    """Annual mean log rent per (ZCTA, year), dropping thin cells.

    Cells with fewer than ``MIN_MONTHS_PER_YEAR`` observed months are
    dropped — thin cells would otherwise dominate the annual mean (design
    section 4, Spec D). Requires ``period_date`` and ``log_zori`` columns.
    """
    return (
        frame.with_columns(pl.col("period_date").dt.year().alias("year"))
        .group_by("ZCTA5CE", "year")
        .agg(
            pl.col("log_zori").mean().alias("ybar"),
            pl.len().alias("n_months"),
        )
        .filter(pl.col("n_months") >= MIN_MONTHS_PER_YEAR)
        .sort("ZCTA5CE", "year")
    )


def _fit_annual(df: pl.DataFrame, x_cols: list[str]) -> FEResult:
    """Two-way FE (ZCTA + year) on the annual collapse, clustered by ZCTA."""
    y = df["ybar"].to_numpy()
    X = np.column_stack([df[c].to_numpy() for c in x_cols])
    zctas = np.asarray(df["ZCTA5CE"].to_list())
    _, units = np.unique(zctas, return_inverse=True)
    years = df["year"].to_numpy()
    return within_fe(y, X, units, years, cluster_ids=units)


def _annual_dict(
    fe: FEResult, df: pl.DataFrame, coef_names: list[str], note: str
) -> dict[str, Any]:
    """Report-ready dict for one Spec D model."""
    dof = fe.n_units - 1
    out: dict[str, Any] = {}
    single = len(coef_names) == 1
    for i, name in enumerate(coef_names):
        coef, se = float(fe.params[i]), float(fe.bse[i])
        suffix = "" if single else f"_{name}"
        out[f"phi{suffix}"] = coef
        out[f"se{suffix}"] = se
        out[f"pvalue{suffix}"] = float(
            2.0 * stats.t.sf(abs(coef / se), df=dof)
        )
    out.update(
        n_cells=fe.n_obs,
        n_units=fe.n_units,
        years=sorted(df["year"].unique().to_list()),
        dof_note=fe.dof_note,
        note=note,
    )
    return out


def _long_difference(
    annual: pl.DataFrame, lodes_panel: pl.DataFrame
) -> dict[str, Any]:
    """Long-difference association per window (design section 4, Spec D):
    cross-sectional OLS of the change in annual mean log rent on the change
    in log access, HC1 robust SEs."""
    lp = lodes_panel.select(
        "ZCTA5CE", "year", pl.col("job_accessibility").log().alias("log_access")
    )
    out: dict[str, Any] = {}
    for y0, y1 in LONG_DIFF_WINDOWS:
        key = f"{y0}_{y1}"
        merged = (
            annual.filter(pl.col("year") == y0)
            .select("ZCTA5CE", pl.col("ybar").alias("ybar0"))
            .join(
                annual.filter(pl.col("year") == y1).select(
                    "ZCTA5CE", pl.col("ybar").alias("ybar1")
                ),
                on="ZCTA5CE",
                how="inner",
            )
            .join(
                lp.filter(pl.col("year") == y0).select(
                    "ZCTA5CE", pl.col("log_access").alias("acc0")
                ),
                on="ZCTA5CE",
                how="inner",
            )
            .join(
                lp.filter(pl.col("year") == y1).select(
                    "ZCTA5CE", pl.col("log_access").alias("acc1")
                ),
                on="ZCTA5CE",
                how="inner",
            )
            .sort("ZCTA5CE")
        )
        window = f"{y0}->{y1}"
        if merged.height < 3:
            out[key] = {
                "window": window,
                "n_zctas": merged.height,
                "note": (
                    f"insufficient data: {merged.height} ZCTAs observed in "
                    f"both {y0} and {y1}"
                ),
            }
            continue
        dy = (merged["ybar1"] - merged["ybar0"]).to_numpy()
        dx = (merged["acc1"] - merged["acc0"]).to_numpy()
        fit = sm.OLS(dy, sm.add_constant(dx)).fit(cov_type="HC1")
        out[key] = {
            "window": window,
            "coef": float(fit.params[1]),
            "se": float(fit.bse[1]),
            "pvalue": float(fit.pvalues[1]),
            "n_zctas": merged.height,
        }
    return out


def _chase_specs(
    frame: pl.DataFrame, lodes_panel: pl.DataFrame
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Spec D: (lagged, lead-falsification, contemporaneous, long-difference).

    All written up as predictive association, never causal: FE consistency
    would need strict exogeneity, which access does not plausibly satisfy
    (design section 4, Spec D).
    """
    annual = collapse_annual(frame)
    lp = lodes_panel.select(
        "ZCTA5CE", "year", pl.col("job_accessibility").log().alias("log_access")
    )
    lagged = lp.rename({"log_access": "log_access_lag"}).with_columns(
        (pl.col("year") + 1).alias("year")
    )
    lead = lp.rename({"log_access": "log_access_lead"}).with_columns(
        (pl.col("year") - 1).alias("year")
    )
    contemp = lp.rename({"log_access": "log_access_contemp"})

    df_lag = annual.join(lagged, on=["ZCTA5CE", "year"], how="inner").sort(
        "ZCTA5CE", "year"
    )
    df_lead = df_lag.join(lead, on=["ZCTA5CE", "year"], how="inner").sort(
        "ZCTA5CE", "year"
    )
    df_contemp = annual.join(
        contemp, on=["ZCTA5CE", "year"], how="inner"
    ).sort("ZCTA5CE", "year")

    chase_lagged = _annual_dict(
        _fit_annual(df_lag, ["log_access_lag"]),
        df_lag,
        ["lag"],
        "predictive association — no causal claim (design section 4, Spec D)",
    )
    chase_lead = _annual_dict(
        _fit_annual(df_lead, ["log_access_lag", "log_access_lead"]),
        df_lead,
        ["lag", "lead"],
        (
            "falsification: lead access added to the lagged model — a "
            "significant lead coefficient means feedback, not chasing"
        ),
    )
    chase_contemp = _annual_dict(
        _fit_annual(df_contemp, ["log_access_contemp"]),
        df_contemp,
        ["contemp"],
        "contemporaneous variant (robustness to the lag choice)",
    )

    return chase_lagged, chase_lead, chase_contemp, _long_difference(
        annual, lodes_panel
    )


def analyze_rq4(
    cross_df: pl.DataFrame,
    zori_panel: pl.DataFrame,
    lodes_panel: pl.DataFrame,
    acs2019_df: pl.DataFrame,
) -> RQ4Results:
    """Full RQ4 analysis: Specs A, B, C, C-med, D (pure computation, no I/O).

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
        Spec A (two-phase break + robustness suite), Spec B event study,
        Spec C access model, Spec C-med mediation, and Spec D chase models
        with long differences.
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

    # --- Spec B: event study (trimmed sample; the fine post bins are how
    # the transition window is examined, so no transition drop here) --------
    event_study = _event_study(frame)

    # --- Specs C / C-med: time-varying access, truncated at last LODES year -
    frame_c = _access_frame(frame, lodes_panel)
    access_model = _access_model(frame_c, lodes_panel)
    mediation = _mediation(frame_c)

    # --- Spec D: annual predictive association + long differences -----------
    chase_lagged, chase_lead, chase_contemp, long_difference = _chase_specs(
        frame, lodes_panel
    )

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

    return RQ4Results(
        gradient_model_joint=joint,
        gradient_models_single=singles,
        gradient_model_pooled=pooled,
        wald_break=wald_break,
        bootstrap_pvalues=bootstrap_pvalues,
        event_study=event_study,
        access_model=access_model,
        mediation=mediation,
        chase_model_lagged=chase_lagged,
        chase_model_lead=chase_lead,
        chase_model_contemp=chase_contemp,
        long_difference=long_difference,
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
