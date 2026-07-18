---
title: "Did COVID Reprice the Commute? Two-Phase Repricing of the Commute Gradient in Nine U.S. Metro Rental Markets"
author: "Charles Coonce"
date: "July 2026 — working paper draft v0.1"
abstract: |
  Using a 102,773-row monthly ZIP-code-level rent panel (Zillow Observed Rent Index, 2015--2026) across nine U.S. metropolitan areas, I estimate whether the pre-existing commute gradient repriced across the COVID-19 break in each metro's covered rental submarket. Per-metro two-way fixed-effects regressions interact three pre-COVID (2019-vintage) gradient measures — average commute time, distance to the central business district, and gravity-model job accessibility — with a two-phase structural break separating the pandemic disruption (2020-03 through 2021-12) from the partial return-to-office era (2022 onward). Where repricing occurred, it favored the periphery: commute-gradient interactions are positive in Phoenix, Denver, Atlanta, and Chicago; job-accessibility interactions are negative in Los Angeles, Dallas--Fort Worth, and Atlanta in both phases, and in the disruption phase in Phoenix and Chicago; Seattle's repricing runs through CBD distance. With the single exception of Chicago's job-accessibility channel, no significant disruption-phase effect returns to zero in the return-to-office phase, and in several metros the later-phase point estimates are larger. The paper's contribution is equal parts finding and discipline: event-study pre-trend checks demote three metros to "trend plus break," a wild cluster bootstrap at coarse spatial clusters sustains only a handful of metro-channel results, and one metro is reported as uninformative on thin identification. The strictly-clean-and-robust list is short; the directional consistency across nine metros is the stronger result.
geometry: margin=1.1in
fontsize: 11pt
numbersections: true
---

# Introduction

For a century of urban economics, the price of housing has embedded the price of proximity: rents fall with distance from employment centers because commuting is costly, the equilibrium traced by the monocentric bid-rent tradition of Alonso, Muth, and Mills. COVID-19 delivered the sharpest shock that equilibrium has ever received. If work can be done at home, the commute a household avoids by paying central rents is worth less — and the gradient should flatten: peripheral, long-commute locations gain value relative to job-rich cores.

A rapidly assembled literature documented exactly this during the pandemic's first two years: the "donut effect" of rent and price declines in dense urban cores relative to suburbs (Ramani and Bloom 2021), the flattening of the bid-rent curve across the largest U.S. metros (Gupta, Mittal, Peeters, and Van Nieuwerburgh 2022), and house-price growth concentrated where remote-work exposure was highest (Mondragon and Wieland 2022). The open questions in 2026 are no longer *whether* the disruption happened but *whether it stuck*, *where* it happened, and *how much of the evidence survives honest inference* — questions the return-to-office era makes answerable for the first time.

This paper asks those questions of nine U.S. metropolitan areas — Atlanta, Chicago, Dallas--Fort Worth, Denver, Los Angeles, Memphis, Miami, Phoenix, and Seattle — using a monthly ZIP-code-level rent panel spanning January 2015 through mid-2026: 62 pre-break and 75 post-break estimation months in every metro. Three design choices distinguish the exercise.

First, **the gradient is measured before the treatment**. The interaction regressors are fixed pre-COVID vintages: average commute time from the ACS 2015--2019 5-year release, geometric distance to the CBD, and log gravity-model job accessibility built from 2019 LODES employment counts. Post-2020 vintages of these same measures are themselves outcomes of the shock (commuting behavior and job geography both moved), and interacting them with a post-COVID dummy would conflate "COVID repriced the pre-existing gradient" with "COVID moved the measured gradient."

Second, **the break is two-phase**. A single post-COVID dummy averages over a documented non-monotone path — disruption-era repricing followed by partial return-to-office re-steepening — making a near-zero coefficient uninterpretable. Separating Post1 (2020-03 to 2021-12) from Post2 (2022-01 onward) lets the data distinguish persistent repricing from reversal, which is precisely the question the 2026 vantage point makes answerable.

Third, **the honesty rails are co-headline**. Every specification travels with an event-study pre-trend check (was the "repricing" already underway before March 2020?), a wild cluster bootstrap at coarse spatial clusters (are the conventional standard errors understated for spatially smooth regressors?), single-interaction sign checks (is the joint model's sign collinearity doing the talking?), and explicit identification flags (one metro, Memphis, identifies the break on only 12 ZIP-code areas and is reported as uninformative). The paper's summary result is deliberately two-sided: the periphery-favoring direction is remarkably consistent across nine metros, and the subset of metro-channel results that survives every check is small.

# Related work

Ramani and Bloom (2021) coined the donut effect: within large U.S. metros, rents and prices in dense central areas fell relative to suburban rings during 2020--21, with migration flows to match. Gupta et al. (2022) estimated bid-rent functions before and during the pandemic across the 30 largest U.S. metros and found dramatic flattening in both rents and prices, with heterogeneity tied to remote-work prevalence. Mondragon and Wieland (2022) attribute a large share of aggregate 2019--2021 house-price growth to remote work; Howard, Liebersohn, and Ozimek (2023) trace the mechanism through housing demand. Brueckner, Kahn, and Lin (2023) embed work-from-home in a spatial equilibrium model and derive exactly the cross-city and within-city repricing this paper measures. On the measurement side, Dingel and Neiman (2020) classify occupations by teleworkability — the natural exposure measure for a mechanism test this paper defers to future work.

This paper's marginal contribution to that literature is threefold: (i) a longer window — through mid-2026, spanning four years of return-to-office — where most donut-effect estimates end in 2021--22; (ii) mid-size and Sunbelt metros (Memphis, Phoenix, Denver) alongside the coastal giants that dominate the flattening literature; and (iii) an inference discipline calibrated to the setting: cluster-robust inference at the unit level is known to understate uncertainty for spatially aggregated regressors (Barrios, Diamond, Imbens, and Kolesár 2012), and few-cluster wild bootstrap methods (Cameron and Miller 2015; Webb 2023) are applied here as a co-equal robustness layer rather than a footnote.

# Data

## Sources and panel construction

The outcome is the Zillow Observed Rent Index (ZORI) at ZIP-code level: a repeat-weighted index of asking rents across the full rental stock. I use the smoothed **non-seasonally-adjusted** series. The choice is deliberate: Zillow re-estimates seasonal factors over the full sample at each release, so current-vintage pre-2020 seasonally-adjusted values embed post-2020 information — an anticipation artifact located exactly at the break under study. Sample-month fixed effects absorb common seasonality anyway, so seasonal adjustment buys nothing and costs look-ahead. ZIP codes are treated as ZCTAs (ZIP Code Tabulation Areas), a documented approximation inherited from the underlying data pipeline.

The committed panel spans January 2015 through June 2026 — 138 months, 102,773 ZIP-month observations across the nine metros. Because Zillow revises published history between pulls (trailing smoothing re-estimates recent months at each release), the panel is committed behind a *revision gate*: each rebuild replaces the panel wholesale with one coherent Zillow vintage, and the gate quantifies and bounds the revisions between vintages (structural checks fail the build; bounded revisions are reported). Every analysis result is thereby reproducible as of a recorded pull.

The three gradient regressors are fixed pre-COVID measures per ZCTA:

- **Commute time** (`commute_min_proxy_2019`): workers-weighted average one-way commute in minutes, ACS 5-year 2015--2019 release (table B08303), computed at ZCTA geography.
- **CBD distance** (`distance_to_cbd_km`): geometric distance from the ZCTA centroid to the metro's central business district point (dual-CBD for Dallas--Fort Worth); vintage-free.
- **Job accessibility** (log `job_accessibility_2019`): a gravity index, $\sum_j \text{jobs}_j \exp(-d_{ij}/10\text{km})$, over the metro's census tracts, built from 2019 LEHD LODES workplace employment.

An annual LODES accessibility panel (2015--2023) supports the secondary time-varying specifications.

## Coverage and estimand

ZORI publishes a ZIP-month cell only where listing volume clears a threshold. Coverage is therefore selected: 70--96% of each metro's ZCTAs appear cross-sectionally (Chicago 70%, Atlanta 96%; Table 2), far fewer in the early years (Chicago and Seattle start at 9% of ZCTAs in 2015), and covered areas are systematically larger, denser rental submarkets. Three consequences discipline every claim in this paper. First, all results describe the *covered rental submarket* — no claim extends to uncovered ZCTAs. Second, the unweighted ZCTA-level regressions estimate *average covered-ZCTA* repricing, not renter-weighted repricing (a renter-weighted variant is reported as robustness). Third, "repricing" means the listing index moved — an amalgam of price and listing-composition change; no hedonic adjustment is possible at this altitude. And because every ZCTA is treated by COVID, there is no control group: estimates are within-metro *relative* descriptions, not causal effects of the pandemic.

Table 2 summarizes the covered samples and the three gradient regressors.

| Metro | Covered / total ZCTAs | Commute 2019, min | CBD distance, km | Log job access 2019 |
|---|---:|---:|---:|---:|
| Phoenix | 131 / 150 | 29.2 (4.5) | 29.0 (19.5) | 12.00 (1.24) |
| Los Angeles | 246 / 270 | 34.5 (3.5) | 21.8 (12.0) | 13.22 (0.60) |
| Dallas--Fort Worth | 177 / 190 | 30.4 (5.4) | 21.6 (14.0) | 12.40 (0.80) |
| Memphis | 39 / 52 | 25.3 (3.9) | 20.0 (13.2) | 11.58 (0.76) |
| Denver | 90 / 103 | 29.8 (3.5) | 16.7 (10.0) | 12.49 (0.61) |
| Atlanta | 112 / 117 | 34.1 (5.1) | 25.3 (14.9) | 12.30 (0.74) |
| Chicago | 204 / 291 | 35.1 (4.5) | 32.6 (19.5) | 12.76 (0.71) |
| Seattle | 125 / 150 | 33.7 (4.5) | 29.4 (17.9) | 12.14 (0.84) |
| Miami | 171 / 180 | 32.1 (5.5) | 44.8 (33.3) | 12.31 (0.67) |

Table: **Table 2 — Covered ZCTAs and gradient regressors, mean (SD), computed on each metro's ZORI-covered ZCTA set.**

# Empirical design

## Specification

All estimation is per metro. The headline specification is a two-way fixed-effects structural break on log rent:

$$
\log(\text{zori}_{it}) = \alpha_i + \gamma_t + \sum_{x} \left[ \beta^{P1}_{x} (x_i \times \text{Post1}_t) + \beta^{P2}_{x} (x_i \times \text{Post2}_t) \right] + \varepsilon_{it}
$$

where $\alpha_i$ are ZCTA fixed effects, $\gamma_t$ are sample-month fixed effects (one dummy per calendar month, absorbing metro-wide shocks and seasonality), $x$ ranges over the three 2019-vintage gradient measures, $\text{Post1}_t = \mathbf{1}[2020\text{-}03 \le t \le 2021\text{-}12]$ (disruption phase) and $\text{Post2}_t = \mathbf{1}[t \ge 2022\text{-}01]$ (partial return-to-office phase). Main effects of $x_i$ are absorbed by $\alpha_i$ and phase main effects by $\gamma_t$; only the interactions are identified — which is the question. The final month of each vintage is trimmed (provisional data), leaving 62 pre-break and 75 post-break months in the headline sample; a co-headline variant additionally drops the 2020-03 to 2020-05 transition window (72 post-break months) and leaves every headline coefficient essentially unchanged in all nine metros.

The donut hypothesis predicts $\beta^{P1}_{\text{commute}} > 0$, $\beta^{P1}_{\text{distance}} > 0$, $\beta^{P1}_{\text{access}} < 0$; the Post2 set answers "did it stick?" Because the three gradients are mutually correlated and spatially smooth, each metro also reports three single-interaction models; where joint and single models disagree, the disagreement is collinearity speaking, and the per-metro verdicts lean on whichever pattern is stable across both.

An event study (Spec B) replaces the phase dummies with event-time bins relative to 2020-03 (base bin 2019-03 to 2020-02; 12-month pre bins, 6-month post bins through early 2022, 12-month bins after). Flat pre-break coefficients establish the absence of differential pre-trends along the gradient, so the break coefficients read as departures from a flat pre-path; a drifting pre-path demotes them to "trend plus break," and the per-metro verdicts report exactly that. (With every ZCTA treated, this check bears on the descriptive reading — trend versus break — not on a causal parallel-trends assumption, which the estimand does not invoke.) Event-study figures carry per-bin identifying-ZCTA counts on a secondary axis, because the earliest bins are thin in several metros (Memphis 7, Denver 12, Seattle 17 ZCTAs).

Two secondary specifications — a time-varying annual accessibility regressor (2015--2023, no carry-forward) and an annual rents-on-lagged-access predictive association with a lead-term falsification — are reported but deliberately kept secondary; the lead-term falsification fails (the *lead* of accessibility is significant) in six of nine metros, so the rents-and-jobs association reads as feedback, not "rents chase jobs."

## Inference

Estimation is by the within transform with standard errors clustered by ZCTA, robust to the severe serial correlation a smoothed monthly index induces. The small-sample correction deliberately rescales the clustered covariance by $(N-K)/(N-K-G_{\text{absorbed}})$ — the conservative direction relative to the Cameron--Miller/reghdfe convention of omitting absorbed fixed effects from $K$; a reviewer should read the slightly inflated standard errors as a choice, not an error.

Unit-level clustering is nonetheless known to understate uncertainty when regressors are spatially smooth (Barrios et al. 2012) — and CBD distance is mechanically so. Each metro therefore also reports wild cluster bootstrap p-values (Cameron and Miller 2015), with Webb weights (Webb 2023) given the small cluster counts, re-clustered at the 3-digit ZIP prefix — spatially coherent USPS sectionals, 4 to 15 per metro. Finally, per-metro identifying counts ($n$ of ZCTAs observed on both sides of the break) are reported with the headline: Memphis identifies the break on only 12 ZCTAs, its conventional cluster t-statistics are oversized, and it is flagged under-identified and read as uninformative throughout.

# Results

## Two-phase break estimates

Table 1 reports the joint-model interaction coefficients. Units are natural: log-points of rent per commute minute, per kilometer of CBD distance, and per log-point of job accessibility.

| Metro | $n$ ident. | Commute P1 | Commute P2 | Distance P1 | Distance P2 | Access P1 | Access P2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Phoenix | 92 | 0.0037\*\* | 0.0048\* | −0.0021\*\*\* | −0.0025\*\* | −0.0259\* | −0.0259 |
| Los Angeles | 121 | 0.0016 | 0.0002 | 0.0001 | 0.0006 | −0.0582\* | −0.0876\*\* |
| Dallas--Fort Worth | 80 | 0.0010 | 0.0018 | −0.0011\*\*\* | −0.0011\* | −0.0330\*\*\* | −0.0382\*\*\* |
| Memphis † | 12 | 0.0035 | 0.0008 | 0.0006 | 0.0008 | 0.0575 | 0.0246 |
| Denver | 66 | 0.0056\*\*\* | 0.0076\*\*\* | 0.0017 | 0.0026 | 0.0289 | 0.0357 |
| Atlanta | 86 | 0.0077\*\*\* | 0.0136\*\*\* | −0.0032\*\*\* | −0.0042\*\*\* | −0.0460\*\*\* | −0.0711\*\*\* |
| Chicago | 52 | 0.0025\* | 0.0045\*\*\* | 0.0003 | 0.0023\* | −0.0585\* | −0.0308 |
| Seattle | 71 | 0.0015 | 0.0039\*\* | 0.0061\*\*\* | 0.0063\*\*\* | 0.0714\* | 0.0600 |
| Miami | 73 | −0.0001 | −0.0006 | 0.0012\*\*\* | 0.0008\* | 0.0084 | −0.0079 |

Table: **Spec A joint model, two-phase break coefficients (2019-vintage regressors).** \* p<0.05, \*\* p<0.01, \*\*\* p<0.001, conventional ZCTA-clustered. "$n$ ident." counts ZCTAs observed both pre- and post-break. † Memphis is under-identified (12 ZCTAs); its row is reported for completeness and read as uninformative. Joint Wald tests on each phase's interaction set reject at p<0.0001 in every metro except Memphis (p = 0.60 / 0.97).

Three patterns organize the table. **First, where repricing happened, it favored the periphery.** Positive commute interactions (Phoenix, Denver, Atlanta, Chicago), negative access interactions (Phoenix, LA, DFW, Atlanta, Chicago in the disruption phase), and Seattle's positive distance interactions all point the same way: covered ZCTAs far from jobs gained rent relative to job-rich cores. No metro shows core-favoring repricing that survives both the single-interaction check and the pre-trend check. **Second, the repricing largely did not reverse.** The one clean fade is Chicago's access effect (−0.0585 to an insignificant −0.0308); elsewhere no significant Post1 effect returns to zero in Post2, and in Atlanta, Denver, Los Angeles (access), and Chicago (commute) the Post2 point estimate exceeds Post1 (point-estimate comparisons; no formal Post2−Post1 test is reported). Four years into return-to-office, the disruption-era reshuffle has stuck or deepened. **Third, the channels differ by metro.** In the joint model, Los Angeles reprices through job accessibility alone (commute and distance conditionally null throughout, in the study's cleanest event study — though all three of LA's marginal estimates are periphery-favoring; Table A1); Denver reprices through commute time; Seattle through CBD distance; Miami shows essentially no COVID-specific repricing.

**Conditional versus marginal signs.** Because the three gradients are mutually correlated, Table 1's joint-model coefficients are conditional loadings, and the negative distance interactions in Phoenix, DFW, and Atlanta illustrate why that matters: each collapses to approximately zero in its single-interaction model (Post1 marginal estimates +0.0002, −0.0000, and −0.0001, all p > 0.59) — conditional artifacts of collinearity, not evidence of core-favoring repricing. The reverse disagreement appears in Seattle, whose access interaction is +0.0714 in the joint model but −0.1080 (p < 0.0001) marginally: Table 1's one apparently significant core-favoring coefficient reverses sign in the single-interaction model. Appendix Table A1 reports the marginal estimates for all nine metros; they are *more* uniformly periphery-favoring than the joint model — job accessibility negative and significant in eight of nine metros (all but under-identified Memphis), commute time positive and significant in seven, distance positive in the five metros where it is significant. The single marginal core-favoring estimate, Miami's negative commute interaction (−0.0033, p = 0.0068), sits on the drifting pre-path that demotes all of Miami's results.

**Magnitudes.** Atlanta's commute × Post2 coefficient of 0.0136 implies that a covered ZCTA with a 10-minute-longer 2019 average commute gained roughly 14% in relative rent by the return-to-office era ($e^{0.136}-1$) — with the caveat that Atlanta is a trend-plus-break metro, so part of that accumulation continues a pre-existing steepening. Denver's 0.0076 implies about 8% per 10 minutes. Scaled by within-metro dispersion (Table 2), a one-standard-deviation commute difference (3.5--5.5 minutes) maps to roughly 2--7% relative rent effects in Post2 across the metros with significant commute repricing — economically meaningful without being implausible.

## Pre-trend verdicts

The event studies discipline the structural-break reading. Los Angeles is the cleanest: all pre-bins statistically indistinguishable from base for all three regressors — the post-break movement is not the continuation of a pre-existing path. Chicago's commute pre-path sits on zero (a clean break) while its access pre-path drifts. Denver's commute pre-bins are significantly below base — part of its post-break rise continues a pre-existing steepening. Phoenix (distance) and DFW (distance and access) drift. Atlanta drifts on all three regressors — its large and growing coefficients read as the *acceleration* of a pre-existing periphery-ward steepening, not a clean break. Seattle shows the steepest pre-trends in the study, running straight into its bootstrap-robust distance result. Miami's tiny distance effect sits on a significant pre-existing path. Memphis's event study is uninformative (7--12 identifying ZCTAs per pre-bin).

The demotions matter for reading Table 1: Atlanta, Seattle, and Miami's headline coefficients are "trend plus break," and Denver's commute channel, Phoenix's distance channel, and DFW's distance and access channels carry partial trend components.

## Spatial-cluster robustness

Re-clustering at the 3-digit ZIP prefix with Webb-weight wild bootstrap thins the significance map considerably. At p<0.05 the bootstrap sustains: Seattle's *positive* distance interaction in both phases (p = 0.014 / 0.021, the study's most bootstrap-robust result), DFW's *negative* access interaction in both phases (p = 0.026 / 0.049), Denver's disruption-phase set (p $\le$ 0.042), and the disruption-phase distance interactions in Phoenix (p = 0.030) and Atlanta (p = 0.032). Two of these demand qualification. The Phoenix and Atlanta distance survivors are the *negative* conditional loadings discussed above — Phoenix's collapses to null marginally, so it carries no evidential weight on its own, and Atlanta's marginal distance estimate is likewise null (−0.0001, p = 0.85). And Denver's bootstrap set includes its distance and access channels, which were never conventionally significant (ZCTA-clustered p = 0.14 and 0.10) — a case where *coarser* clustering yields *smaller* p-values, the opposite of the understatement concern motivating the exercise, and a reminder that 4-to-15-cluster bootstrap p-values carry their own finite-sample noise. Everything else — including every Chicago result and LA's access channel (p $\approx$ 0.11--0.13) — fails the coarse-cluster bar. Memphis's ZCTA-level bootstrap is consistent with its uninformative verdict (all p $\ge$ 0.28).

The two robustness layers cut against different metros: Seattle is bootstrap-robust but pre-trend-contaminated; Los Angeles is pre-trend-clean but narrowly misses the bootstrap bar; Denver's commute channel is bootstrap-robust but carries a pre-existing steepening. No metro-channel result clears every check cleanly — which is the honest summary of nine-metro evidence at this spatial resolution — while the directional consistency (periphery-favoring in every metro where anything moves, on both conditional and marginal readings) is the finding that no individual check dislodges.

## Composition and selection

ZCTAs entering the panel after December 2019 are more peripheral than incumbents on all three gradients in seven of nine metros, so incumbent-identified estimates likely *understate* periphery repricing where entrants are peripheral. A balanced-subpanel bound (ZCTAs in-sample by January 2019) sits close to the headline in every metro and changes no substantive conclusion.

# Robustness

**Index choice.** Re-running the headline specification for Phoenix, Los Angeles, and Chicago against a local build of the seasonally-adjusted ZORI series moves every interaction coefficient by well under one standard error (the largest shift is 0.18 SE), with no sign changes and no significance crossings. The non-SA choice is not driving the results.

**Renter weighting.** Weighting ZCTAs by renter prevalence (renter share times population — a different estimand: renter-weighted rather than average-covered-ZCTA repricing) changes no qualitative verdict: strong metros hold or strengthen (Denver commute Post2 0.0076 to 0.0087; Atlanta 0.0136 to 0.0140; Phoenix strengthens on all three regressors), nulls stay null, and no coefficient changes sign. The one notable movement is Chicago's commute channel, which attenuates in the disruption phase but *strengthens* in Post2 (0.0039, p = 0.0007) — Chicago's return-to-office-era commute repricing is, if anything, concentrated in renter-heavy ZCTAs.

**Transition window.** Dropping 2020-03 through 2020-05 (the months where trailing smoothing spreads the shock) leaves every headline coefficient essentially unchanged in all nine metros.

**Secondary specifications stay secondary.** Within-ZCTA annual accessibility is significantly negative in LA, Chicago, and Seattle, positive in Miami, null elsewhere. The rents-on-lagged-access association fails its lead-term falsification in six metros and is reported as feedback, not causation. Mediation shares through contemporaneous job relocation are unstable across metros and are not leaned on.

# What this paper does not claim

No causal effect of COVID (every ZCTA is treated; no control group). No claim about uncovered ZCTAs — the 4--30% of each metro's ZIP-code areas, systematically thinner rental markets, that ZORI does not publish. No decomposition of price versus listing-composition change. No welfare or affordability-burden claims — the outcome is a rent index, not rent-to-income. No cross-metro pooled estimate — per-metro estimation, cross-metro comparison only. And no mechanism test yet: the repricing is *consistent with* the remote-work story, but this paper does not measure teleworkability exposure.

# Conclusion

Across nine U.S. metros observed through mid-2026, COVID-era repricing of the commute gradient was periphery-favoring wherever it registered, and it largely did not reverse — in several metros the point estimates deepened — through four years of return-to-office. The evidence is strongest as a directional pattern and deliberately modest as a set of individually robust point estimates: pre-trend checks demote three metros to trend-plus-break, coarse-cluster bootstrap inference sustains only a handful of metro-channel results, and one metro is uninformative on thin identification.

The natural next step is a mechanism test: interacting a pre-COVID teleworkability exposure — Dingel--Neiman occupation shares (Dingel and Neiman 2020) applied to each ZCTA's 2019 LODES industry mix — with the same two-phase break, asking whether the repricing loads on remote-work exposure over and above raw commute geometry. That test, along with Conley spatial-HAC standard errors as a continuous middle ground between the unit-cluster and coarse-cluster inference regimes, and single-family versus multifamily index tiers to separate price from composition, is queued in the project's public issue tracker.

# Figures

![Los Angeles event study — the cleanest pre-trend in the study. Gradient-interaction coefficients by event-time bin (base = 2019-03 to 2020-02); bars show identifying-ZCTA counts per bin. Pre-break coefficients are statistically indistinguishable from base for all three regressors (the elevated earliest bin rests on 30 ZCTAs and stays inside its CI); job-accessibility repricing emerges after 2020-03 and deepens.](../../figures/LA/rq4_la_event_study.png)

![Denver two-phase gradient repricing (pre-break = 0 reference). The commute-gradient interaction is positive in the disruption phase and larger in the return-to-office phase — the study's strongest commute repricing; distance and access interactions carry wide confidence intervals.](../../figures/DEN/rq4_den_gradient_phases.png)

# Appendix

| Metro | Commute P1 | Commute P2 | Distance P1 | Distance P2 | Access P1 | Access P2 |
|---|---:|---:|---:|---:|---:|---:|
| Phoenix | 0.0034\*\*\* | 0.0037\*\*\* | 0.0002 | −0.0000 | −0.0110\*\* | −0.0088 |
| Los Angeles | 0.0051\*\*\* | 0.0055\*\* | 0.0029\*\*\* | 0.0046\*\*\* | −0.0636\*\*\* | −0.0991\*\*\* |
| Dallas--Fort Worth | 0.0027\* | 0.0040\* | −0.0000 | 0.0002 | −0.0271\*\*\* | −0.0361\*\* |
| Memphis † | −0.0016 | 0.0004 | −0.0002 | 0.0003 | 0.0225 | 0.0027 |
| Denver | 0.0055\*\*\* | 0.0084\*\*\* | 0.0011\*\* | 0.0020\*\* | −0.0192\*\* | −0.0351\*\* |
| Atlanta | 0.0068\*\*\* | 0.0135\*\*\* | −0.0001 | 0.0011 | −0.0285\*\* | −0.0662\*\*\* |
| Chicago | 0.0056\*\*\* | 0.0062\*\*\* | 0.0025\*\*\* | 0.0037\*\*\* | −0.0832\*\*\* | −0.1189\*\*\* |
| Seattle | 0.0094\*\*\* | 0.0131\*\*\* | 0.0039\*\*\* | 0.0049\*\*\* | −0.1080\*\*\* | −0.1333\*\*\* |
| Miami | −0.0033\*\* | −0.0027\* | 0.0011\*\*\* | 0.0009\*\*\* | −0.0511\*\*\* | −0.0481\*\* |

Table: **Table A1 — Spec A single-interaction (marginal) models: each gradient interacted with Post1/Post2 in its own two-way FE regression.** \* p<0.05, \*\* p<0.01, \*\*\* p<0.001, conventional ZCTA-clustered. † Memphis under-identified. Full per-metro tables with standard errors are in the repository's `data/processed/<METRO>/rq4_summary_<METRO>.md`.

# References

- Barrios, T., R. Diamond, G. W. Imbens, and M. Kolesár (2012). "Clustering, Spatial Correlations, and Randomization Inference." *Journal of the American Statistical Association* 107(498): 578--591.
- Brueckner, J. K., M. E. Kahn, and G. C. Lin (2023). "A New Spatial Hedonic Equilibrium in the Emerging Work-from-Home Economy?" *American Economic Journal: Applied Economics* 15(2): 285--319.
- Cameron, A. C., and D. L. Miller (2015). "A Practitioner's Guide to Cluster-Robust Inference." *Journal of Human Resources* 50(2): 317--372.
- Dingel, J. I., and B. Neiman (2020). "How Many Jobs Can Be Done at Home?" *Journal of Public Economics* 189: 104235.
- Gupta, A., V. Mittal, J. Peeters, and S. Van Nieuwerburgh (2022). "Flattening the Curve: Pandemic-Induced Revaluation of Urban Real Estate." *Journal of Financial Economics* 146(2): 594--636.
- Howard, G., J. Liebersohn, and A. Ozimek (2023). "The Short- and Long-Run Effects of Remote Work on U.S. Housing Markets." *Journal of Financial Economics* 150(1): 166--184.
- Mondragon, J. A., and J. Wieland (2022). "Housing Demand and Remote Work." NBER Working Paper 30041.
- Ramani, A., and N. Bloom (2021). "The Donut Effect of Covid-19 on Cities." NBER Working Paper 28876.
- Webb, M. D. (2023). "Reworking Wild Bootstrap-Based Inference for Clustered Errors." *Canadian Journal of Economics* 56(3): 839--858.
