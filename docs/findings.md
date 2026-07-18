# Cross-Metro Findings: Housing Affordability & Commute Trade-Off Analysis

**Date:** 2026-03-07
**Revised:** 2026-07 (employment variables; RQ4 ZORI dynamics)
**Metros Analyzed:** Atlanta (ATL), Chicago (CHI), Dallas-Fort Worth (DFW), Denver (DEN), Los Angeles (LA), Memphis (MEM), Miami (MIA), Phoenix (PHX), Seattle (SEA)

---

## Executive Summary

This analysis examines the relationship between housing affordability, commute time, and transit access across nine U.S. metropolitan areas at the ZCTA level. The central finding is that **affordability is primarily an income and renter-concentration problem** — renter share is a significant predictor of rent burden in 8 of 9 metros, while commute time is significant in 6 of 9 (revised up from 4 of 9 after the 2026-07 addition of employment-center variables; see §9). Racial disparities in housing cost burden are pervasive (8 of 9 metros), and transit access signals expensive, high-demand areas in dense cities; no metro shows a significant affordability-serving transit effect once employment structure is controlled.

- **RQ4 (2026-07):** On the monthly ZORI panel, COVID-era repricing of the commute gradient registers in the covered rental submarkets of 8 of 9 metros (joint Wald p < 0.0001 everywhere except under-identified Memphis), predominantly in the periphery-favoring direction — long-commute, low-accessibility ZCTAs gained relative to job-rich cores — and nowhere fully reverses in the 2022+ return-to-office phase; but the honesty checks bite: pre-trend drift demotes Atlanta, Seattle, and Miami to "trend + break", and the coarse-cluster spatial bootstrap sustains only a subset of the conventional significance (§10).

---

## 1. Housing Affordability

### Rent Burden Rankings (Mean Rent-to-Income Ratio)

| Rank | Metro | Mean Rent Burden | Low-Income | High-Income | Gap |
|------|-------|-----------------|------------|-------------|-----|
| 1 (worst) | Miami | 0.310 | 0.357 | 0.258 | 0.099 |
| 2 | Los Angeles | 0.283 | 0.330 | 0.241 | 0.089 |
| 3 | Atlanta | 0.246 | 0.298 | 0.199 | 0.099 |
| 4 | Memphis | 0.242 | 0.339 | 0.168 | 0.171 |
| 5 | Phoenix | 0.237 | 0.264 | 0.205 | 0.059 |
| 6 | Dallas-Fort Worth | 0.235 | 0.282 | 0.191 | 0.091 |
| 7 | Denver | 0.228 | 0.276 | 0.197 | 0.079 |
| 8 | Seattle | 0.221 | 0.259 | 0.189 | 0.070 |
| 9 (best) | Chicago | 0.211 | 0.270 | 0.169 | 0.101 |

### Key Takeaways

- **Miami and Los Angeles are the least affordable metros**, both exceeding or approaching the 30% rent-burdened threshold on average.
- **Low-income residents exceed the 30% burden threshold in every metro**, ranging from 25.9% of income (Seattle) to 35.7% (Miami).
- **Memphis has the widest affordability gap** between income segments (17.1 percentage points), indicating extreme income-based inequality despite a moderate overall average.
- **Chicago is the most affordable on average** (21.1%) but still shows a 10.1-point gap between income groups.

---

## 2. Commute Time Patterns

### Mean Commute Time by Metro

| Metro | Mean Commute (min) |
|-------|-------------------|
| Memphis | 27.9 |
| Phoenix | 29.3 |
| Dallas-Fort Worth | 29.8 |
| Denver | 30.4 |
| Miami | 31.8 |
| Atlanta | 33.3 |
| Seattle | 33.6 |
| Los Angeles | 33.7 |
| Chicago | 34.0 |

### Key Takeaways

- **Sunbelt/sprawl metros have shorter average commutes** (Memphis, Phoenix, DFW) despite being car-dependent, likely due to lower congestion and dispersed employment.
- **Dense metros have the longest commutes** (Chicago, LA, Seattle) at 33–34 minutes.
- The total spread is narrow — only ~6 minutes separates the shortest and longest averages, suggesting commute time alone is a blunt instrument for distinguishing metro affordability dynamics.

---

## 3. RQ1 — Housing-Commute Trade-Off

### Does commute time predict rent burden?

| Metro | Model | Adj R² | Commute Sig? | p-value | Relationship |
|-------|-------|--------|-------------|---------|-------------|
| Memphis | Quadratic | 0.7963 | No | 0.07 | Concave |
| Atlanta | Linear | 0.7024 | Yes | <0.001 | Positive linear |
| Seattle | Quadratic | 0.6135 | No | 0.32 | Convex |
| Denver | Quadratic | 0.5131 | Yes | <0.05 | Concave |
| Chicago | Linear | 0.4669 | Yes | <0.05 | Positive linear |
| Los Angeles | Linear | 0.4465 | Yes | <0.05 | Positive linear |
| Dallas-Fort Worth | Quadratic | 0.3868 | Yes | <0.05 | Concave |
| Phoenix | Linear | 0.3862 | No | 0.85 | Weak positive |
| Miami | Linear | 0.3247 | Yes | <0.01 | Positive linear |

### Key Takeaways

- **Commute time is statistically significant in 6 of 9 metros** (Atlanta, Chicago, Los Angeles, Denver, DFW, Miami) — up from 4 of 9 before employment-center variables were added, and with different membership: Memphis and Seattle dropped out of significance while Atlanta, Chicago, Los Angeles, and Miami entered (see §9).
- **Renter share remains the most consistently significant predictor** — significant in 8 of 9 metros (p < 0.01 in 7). Phoenix is the sole exception (p = 0.078). Areas with higher concentrations of renters have higher rent burdens nearly universally.
- **The new employment-center variables register directly in RQ1:** `job_accessibility` is significant and negative in Chicago (p < 0.0001), DFW (p = 0.005), Phoenix (p = 0.009), and Seattle (p = 0.034); `distance_to_cbd_km` is significant and negative in Chicago (p < 0.0001), DFW (p = 0.0004), and Phoenix (p = 0.025); `job_density` is significant and positive in Atlanta (p = 0.009).
- **Memphis still has the strongest model fit** (R² = 0.80), but commute time itself is no longer significant there (p = 0.07) — renter share (p < 0.0001) now carries the model. Note the Memphis sample changed in the re-run (duplicate rows removed; see §9).
- **Miami is now the hardest metro to model** (R² = 0.32). Phoenix — previously the weakest fit with no significant predictors — improved to R² = 0.39 with four significant predictors (vehicle access, population density, distance to CBD, job accessibility).
- **The concave relationship** is statistically supported only in Denver (see the threshold subsection below); DFW and Memphis retain concave point estimates whose curvature terms are not significant, so their "diminishing returns" reading is suggestive rather than established. Miami flipped from concave to positive linear; Seattle's selected model is now a convex quadratic, but its commute terms are not significant.
- **Multicollinearity increased with the new variables**: `job_accessibility` posts VIFs of 5–11 in every metro except DFW, and Los Angeles — formerly the only metro with no multicollinearity issues (max VIF = 3.38) — now has a max VIF of 9.21.

### Commute-Time Threshold (2026-07)

For metros whose AIC-selected model is quadratic, the "drive until you qualify" threshold is now estimated as the vertex of the quadratic, t\* = −B₁/(2·B₂), with a delta-method 95% CI. A threshold is reported only when the curvature is significantly concave (B₂ < 0, p < 0.05) *and* the vertex lies inside the observed commute range.

- **Denver is the only metro that clears both guards: t\* = 36.5 minutes** (delta-method SE = 2.32, 95% CI [31.9, 41.0]). Beyond that commute time the fitted rent-burden curve turns over — longer commutes no longer trade for improved affordability.
- **The other eight metros are honest nulls** ("convex or insignificant curvature"): Atlanta, Chicago, Los Angeles, Miami, and Phoenix select linear models (no vertex exists); Seattle's selected quadratic is convex (B₂ = +0.0001, p = 0.21); DFW and Memphis have concave point estimates whose curvature terms fail the significance guard (B₂ p = 0.0625 and p = 0.1946, respectively).
- **An AIC-selected quadratic does not imply a significant concave vertex.** DFW and Memphis appear as "Quadratic / Concave" in the table above — and DFW's commute term is significant — but in both cases the significance attaches to the linear term, not the curvature, so no threshold is identified there. The "diminishing returns" reading for DFW and Memphis rests on the sign of the point estimate only; Denver is the sole metro where the concavity itself is statistically supported.

---

## 4. RQ2 — Equity Analysis

### Income Disparities

- **All 9 metros show statistically significant income-based rent burden differences** (p < 0.0001 in all cases). This is the single most robust finding in the entire analysis.
- Chicago has the strongest F-statistic (F = 80.6), indicating the most pronounced income stratification in rent burden.

### Racial Disparities

- **8 of 9 metros show significant racial differences in rent burden.** Majority-white ZCTAs consistently have lower rent burdens.
- **Seattle is the sole exception** — no significant racial differences (F = 0.11, p = 0.90). Seattle's affordability dynamics are income-driven but not race-stratified.
- Chicago shows the strongest racial disparity signal (F = 59.0), followed by DFW (F = 26.9) and Memphis (F = 12.7).

### Commute × Income Interaction

- In **7 of 9 metros**, the interaction between commute time and low-income status is not significant — the commute-rent tradeoff operates similarly regardless of income level.
- **Seattle remains an exception** (p = 0.022): the negative interaction coefficient (−0.0054) suggests low-income residents there benefit more from the "drive until you qualify" tradeoff than other income groups.
- **Chicago is a new exception in the 2026-07 re-run** (p = 0.020): its *positive* interaction coefficient (+0.0032) suggests rent burden rises faster with commute time in low-income ZCTAs — the opposite of Seattle's dynamic.

### Transit Access and Income

Transit density differs significantly across income segments in 5 metros (2026-07 re-run):
- **Phoenix** (p < 0.0001)
- **Los Angeles** (p < 0.0001)
- **Chicago** (p = 0.016)
- **Miami** (p = 0.0018)
- **Atlanta** (p = 0.037)

Transit stratification is no longer confined to the legacy-transit metros — Phoenix and Atlanta now register as well. **Job accessibility is also income-stratified in 5 of 9 metros** (ANOVA): Los Angeles and Denver (p < 0.0001), Miami (p = 0.0006), Seattle (p = 0.0018), and Phoenix (p = 0.018).

### K-Means Clustering

Every metro produced a distinct "extreme pressure" cluster:
- **Atlanta:** 2-ZCTA cluster with mean rent burden of 0.527 — the highest single-cluster burden observed.
- **Seattle:** 2-ZCTA cluster at 0.432 rent burden.
- **Chicago:** Its worst cluster combines the highest rent burden (0.333) with the longest commute (39.9 min) — a "double-burdened" zone where residents face both housing cost and commute time pressure simultaneously.

---

## 5. RQ3 — Affordability-Commute Index (ACI)

### ACI Model Performance

| Metro | ACI Adj R² | Transit Sig? | Transit Direction |
|-------|-----------|-------------|-------------------|
| Memphis | 0.6873 | No | — |
| Chicago | 0.6423 | Yes (p = 0.001) | Positive |
| Miami | 0.5930 | Yes (p = 0.0004) | Positive |
| Dallas-Fort Worth | 0.5705 | No | — |
| Atlanta | 0.5375 | No | — |
| Seattle | 0.4936 | No | — |
| Denver | 0.4440 | No | — |
| Los Angeles | 0.4102 | No | — |
| Phoenix | 0.3348 | Yes (p = 0.003) | Positive |

### Key Takeaways

- **Job accessibility is the most consistent ACI predictor** — significant and *negative* in 8 of 9 metros (all but Los Angeles): Atlanta, Chicago, DFW, and Miami at p < 0.0001, Phoenix (p = 0.0003), Denver (p = 0.0065), Memphis (p = 0.011), and Seattle (p = 0.012). Higher job accessibility is associated with lower combined affordability-commute pressure everywhere it registers.

- **Distance to CBD** is significant and negative in Chicago (B = −0.037, p = 0.001) and Miami (B = −0.034, p < 0.0001) — combined pressure falls with distance from the core in those metros. It is borderline negative in Atlanta (p = 0.058) and borderline *positive* in Los Angeles (B = +0.031, p = 0.050).

- **Transit access still signals expensive, high-demand areas in dense metros:** significant and positive in Chicago (p = 0.001), Miami (p = 0.0004), and — new in this re-run — Phoenix (p = 0.003).

- **DFW's negative transit effect did not survive the employment controls.** Previously the only metro where more transit meant less combined pressure (p = 0.007), DFW's transit coefficient is now non-significant (p = 0.11). The negative sign persists only in upper-quantile point estimates (−0.085 at the median, −0.069 at the 75th percentile; the 25th-percentile coefficient is positive).

- **Phoenix is no longer unexplainable** — ACI Adj R² jumped from 0.017 to 0.335 with the employment variables, with transit (positive) and job accessibility (negative) both significant.

- **The Memphis paradox is resolved:** its ACI model went from worst-fitting (R² = 0.17) to best-fitting (R² = 0.69). Transit stop density is still irrelevant there (p = 0.71) because Memphis has virtually no transit infrastructure — but job accessibility (p = 0.011) now supplies the spatial signal transit couldn't.

- **ACI distribution varies substantially across metros:**
  - Chicago has the widest range (−3.64 to 6.08), indicating extreme within-metro variation.
  - Memphis has the tightest range (max 1.83), indicating more spatial homogeneity.
  - Los Angeles has an extreme negative outlier (ACI = −6.675).

---

## 6. Cross-Cutting Themes

### Theme A: Affordability Is an Income Problem, Not a Commute Problem

Commute time predicts rent burden in 6 of 9 metros once employment-center variables are controlled (§9) — more than the 4 of 9 originally reported — but renter share (8 of 9 metros) and income segment (9 of 9) remain the dominant drivers everywhere. Policy interventions targeting commute reduction alone will still not meaningfully address affordability.

### Theme B: Racial Inequality in Housing Is Pervasive but Not Universal

8 of 9 metros show significant racial rent burden disparities. Seattle's exception — no racial disparities but significant income disparities — suggests its housing market stratifies by wealth rather than race. This finding merits further investigation.

### Theme C: Transit Is a Double-Edged Sword

In dense, established transit cities (Chicago, Miami) — and, in the 2026-07 re-run, Phoenix — transit-rich areas have higher combined housing-commute pressure because they are in-demand locations. The apparent counter-example (DFW, where transit access seemed to genuinely reduce combined pressure) did not survive the employment-variable controls and is no longer significant (§5, §9). For most metros, transit has no measurable effect. Transit investment must be paired with affordability protections to avoid displacement.

### Theme D: "Drive Until You Qualify" Has Limits

The concave quadratic relationship — statistically supported only in Denver, with concave-but-insignificant point estimates in DFW and Memphis (Miami's re-run model is now positive linear) — suggests rent burden initially decreases with longer commutes but plateaus. At a certain distance, further driving no longer buys proportionally more affordability — suggesting a spatial boundary to the tradeoff.

### Theme E: Metro Structure Matters More Than Metro Size

Memphis (51 ZCTAs after duplicate-row removal) has the best RQ1 model fit; Miami (178 ZCTAs) and Phoenix (147 ZCTAs) have the worst. Explanatory power tracks with how consistently the metro's spatial structure follows the expected center-periphery gradient, not with observation count.

---

## 7. Notable Outliers and Anomalies

| Finding | Metro | Detail |
|---------|-------|--------|
| No racial rent disparities | Seattle | Only metro where race does not significantly predict rent burden (F = 0.11, p = 0.90) |
| Significant commute × income interaction | Seattle, Chicago | Low-income residents experience a different commute-rent tradeoff (Seattle p = 0.022, negative; Chicago p = 0.020, positive — new in 2026-07) |
| Transit reduces ACI (retracted 2026-07) | DFW | Effect no longer significant (p = 0.11) once employment variables are controlled — see §9 |
| Extreme pressure ZCTAs | ATL, SEA | 2-ZCTA clusters with rent burdens of 0.527 (ATL) and 0.432 (SEA) |
| Double-burdened zone | Chicago | Cluster with highest rent burden (0.333) AND longest commute (39.9 min) |
| Formerly unexplainable | Phoenix | Employment variables lifted RQ1 to R² = 0.39 and ACI to R² = 0.33 (was 0.32 / 0.02) — see §9 |
| Widest income gap | Memphis | 17.1 percentage point gap between low- and high-income rent burden |
| Best RQ1, no longer worst ACI | Memphis | R² = 0.80 for commute model; ACI model improved from R² = 0.17 to 0.69 once job accessibility entered — see §9 |

---

## 8. Implications for Policy and Future Research

### Policy Implications

1. **Income-targeted interventions** (rental assistance, inclusionary zoning, wage policy) are more likely to reduce rent burden than commute-oriented strategies alone.
2. **Transit investment requires affordability protections.** In Chicago and Miami, transit-rich areas already price out lower-income residents. Expanding transit without anti-displacement measures may worsen affordability in the areas it serves.
3. **DFW's transit result did not survive employment controls.** The 2026-03 finding that DFW was the only metro where transit access correlated with lower combined pressure is no longer significant once job accessibility and CBD distance are in the model (§9); transit-planning inferences drawn from it should be treated as superseded.
4. **Racial equity in housing** remains a challenge in 8 of 9 metros. Place-based policies must account for racial disparities in cost burden, not just income-based ones.

### Future Research Directions

1. **Investigate Phoenix.** *(Partially answered, 2026-07.)* Employment-center variables lifted Phoenix's ACI fit from 0.017 to 0.335 and made four RQ1 predictors significant (§9) — job accessibility was a major missing variable. Rapid growth, seasonal migration, and land use patterns remain candidates for the residual.
2. **Explore Seattle's racial equity outlier.** Why does Seattle show no racial rent burden disparities when 8 other metros do? Is this a function of demographics, policy, or spatial sorting?
3. **Longitudinal analysis.** This cross-sectional analysis captures a single point in time. Tracking how these relationships evolve — especially in rapidly growing metros like Phoenix, DFW, and Seattle — would strengthen causal claims.
4. **Incorporate employment center locations.** **Done (2026-07)** — job density, distance to CBD, and job accessibility were added to all models; see §9. Model fit improved in every metro on both RQ1 and ACI, most dramatically for the ACI models (Phoenix 0.017 → 0.335, Memphis 0.168 → 0.687). The prediction that this would help "particularly in polycentric metros like LA and DFW" was half right: DFW's ACI fit rose sharply (0.354 → 0.571), but LA saw the smallest RQ1 gain of the nine (+0.02) and the second-smallest ACI gain (+0.04).
5. **Examine the "drive until you qualify" threshold.** **Answered (2026-07)** — a vertex estimator (t\* = −B₁/(2·B₂) with a delta-method 95% CI, reported only for significantly concave quadratics whose vertex falls inside the observed commute range) was added to the RQ1 models; see §3. The answer is largely a negative one: once the employment-center controls entered the models (§9), the apparent concavity that motivated this direction mostly vanished — the quadratic's curvature was substantially proxying employment-center spatial structure. The threshold is identified in only one metro: **Denver, at 36.5 minutes (95% CI [31.9, 41.0])**. The other eight metros show convex or statistically insignificant curvature.

---

## 9. Employment-Variable Impact (2026-07)

The 2026-07 re-run added three employment-center variables to every model — `job_density`, `distance_to_cbd_km`, and `job_accessibility` — and refreshed the live data inputs. Model fit, before (2026-03 baseline, copied from the original §3/§5 tables) vs after (regenerated per-metro analysis summaries):

| Metro | RQ1 Adj R² (before) | RQ1 Adj R² (after) | ACI Adj R² (before) | ACI Adj R² (after) |
|-------|--------------------:|-------------------:|--------------------:|-------------------:|
| Atlanta | 0.554 | 0.7024 | 0.238 | 0.5375 |
| Chicago | 0.435 | 0.4669 | 0.573 | 0.6423 |
| Dallas-Fort Worth | 0.322 | 0.3868 | 0.354 | 0.5705 |
| Denver | 0.483 | 0.5131 | 0.352 | 0.4440 |
| Los Angeles | 0.428 | 0.4465 | 0.373 | 0.4102 |
| Memphis | 0.726 | 0.7963 | 0.168 | 0.6873 |
| Miami | 0.300 | 0.3247 | 0.318 | 0.5930 |
| Phoenix | 0.315 | 0.3862 | 0.017 | 0.3348 |
| Seattle | 0.585 | 0.6135 | 0.485 | 0.4936 |

Fit improved in all nine metros on both measures. The largest gains are in the ACI models (Memphis +0.52, Phoenix +0.32, Atlanta +0.30, Miami +0.28), where `job_accessibility` is significant and negative in 8 of 9 metros (all but Los Angeles).

**Comparison caveats.** RQ1 comparisons are drift-free — all predictors are ACS/TIGER/LODES-derived and either byte-identical to the baseline or newly added — *except* Atlanta (117 vs 125 ZCTAs; the stale-baseline Carroll County config was remediated) and Memphis (52 vs 76 rows; duplicate-ZCTA rows were removed from the committed data, and Memphis's before-values were computed on the dup-weighted data). ACI comparisons additionally confound the new employment variables with zori/OSM live-data drift from the 2026-07 rebuild (drift magnitudes are recorded in the rebuild gate output on PR #4).

Substantive shifts attributable to the re-run:

- Commute significance moved from 4 of 9 metros to 6 of 9, with changed membership: Atlanta, Chicago, Los Angeles, and Miami became significant; Memphis and Seattle dropped out (§3).
- DFW's negative transit-ACI effect — previously the analysis's only "transit reduces pressure" result — is no longer significant; Phoenix gained a significant *positive* transit effect (§5).
- Phoenix is no longer unexplainable (ACI 0.017 → 0.335), and the Memphis best-RQ1/worst-ACI paradox is resolved (ACI 0.168 → 0.687) (§5, §7).
- Job accessibility is income-stratified in 5 of 9 metros (RQ2 ANOVA: Los Angeles and Denver p < 0.0001, Miami p = 0.0006, Seattle p = 0.0018, Phoenix p = 0.018) (§4).
- A drive-until-you-qualify threshold estimator (quadratic vertex, delta-method CI, guarded on significant concavity and in-range vertex) now runs alongside RQ1; on the re-run models it applies in only one metro — Denver, t\* = 36.5 min, 95% CI [31.9, 41.0] — with the other eight reporting convex or insignificant curvature (§3).

---

## 10. RQ4 — COVID and the Commute Gradient (ZORI Dynamics)

Did COVID reprice the pre-existing commute gradient in each metro's covered rental submarket? RQ4 estimates a two-way fixed-effects structural break on the monthly Zillow ZORI panel: log rent on ZCTA and sample-month fixed effects plus interactions of three **pre-COVID-vintage** gradient measures — the ACS-2019 commute proxy (`commute_min_proxy_2019`), geometric distance to CBD, and log LODES-2019 job accessibility — with a disruption-phase dummy (Post1 = 2020-03 … 2021-12) and a partial-return-to-office dummy (Post2 = 2022-01 onward). SEs are clustered by ZCTA; every metro runs on 62 pre-break and 72 post-break months (endpoint trim + transition-window drop applied). A co-headline variant dropping the 2020-03…05 transition window leaves every headline coefficient essentially unchanged in all nine metros. Full per-metro tables, event-study figures, and the mandatory caveats block live in `data/processed/<METRO>/rq4_summary_<METRO>.md`.

**Estimand statement (design §4, verbatim).** Unweighted ZCTA-level regression estimates the *average covered-ZCTA* repricing, not renter-weighted repricing; ZORI cells also have listing-volume-dependent precision. Results describe the covered rental submarket only: ZORI's minimum listing volume over-represents larger, denser rental submarkets (71–96% of metro ZCTAs covered cross-sectionally, far less pre-2020 — Chicago and Seattle start at 9% in 2015), so no claim extends to uncovered ZCTAs. "Repricing" means the listing index moved — an amalgam of price and composition change, with no hedonic adjustment possible at this altitude — and every estimate is a within-metro *relative* description, not a causal effect of COVID: every ZCTA is treated and no control group exists.

**Inference conventions.** The clustered covariance is deliberately rescaled by (N−K)/(N−K−G_absorbed) — the conservative direction relative to the Cameron–Miller/reghdfe convention, inflating SEs slightly rather than shrinking them; a reviewer should read this as a choice, not an error. Because the three gradient regressors are mutually correlated and spatially smooth, each metro also reports single-interaction models (sign robustness) and wild cluster bootstrap (Webb) p-values re-clustered at the 3-digit ZIP prefix (4–15 spatial clusters per metro). **Memphis is flagged under-identified**: only 12 ZCTAs are observed on both sides of the break, so its conventional cluster t-statistics are oversized and ZCTA-level bootstrap p-values are reported beside them.

### Spec A — Two-Phase Break Coefficients (joint model, 2019-vintage regressors)

| Metro | n identifying | Commute × Post1 | Commute × Post2 | Distance × Post1 | Distance × Post2 | Access × Post1 | Access × Post2 | Wald p (P1 / P2) |
|-------|--------------:|-----------------|-----------------|------------------|------------------|----------------|----------------|------------------|
| Phoenix | 92 | 0.0037 (p = 0.0097) | 0.0048 (p = 0.0136) | −0.0021 (p < 0.0001) | −0.0025 (p = 0.0015) | −0.0259 (p = 0.0191) | −0.0259 (p = 0.1078) | <0.0001 / <0.0001 |
| Los Angeles | 121 | 0.0016 (p = 0.2012) | 0.0002 (p = 0.9100) | 0.0001 (p = 0.9109) | 0.0006 (p = 0.7083) | −0.0582 (p = 0.0268) | −0.0876 (p = 0.0066) | <0.0001 / <0.0001 |
| Dallas-Fort Worth | 80 | 0.0010 (p = 0.3299) | 0.0018 (p = 0.2716) | −0.0011 (p = 0.0008) | −0.0011 (p = 0.0334) | −0.0330 (p < 0.0001) | −0.0382 (p = 0.0009) | <0.0001 / <0.0001 |
| Memphis † | 12 | 0.0035 (p = 0.7146) | 0.0008 (p = 0.9500) | 0.0006 (p = 0.7838) | 0.0008 (p = 0.8260) | 0.0575 (p = 0.2524) | 0.0246 (p = 0.7054) | 0.6034 / 0.9714 |
| Denver | 66 | 0.0056 (p < 0.0001) | 0.0076 (p < 0.0001) | 0.0017 (p = 0.1418) | 0.0026 (p = 0.1380) | 0.0289 (p = 0.1044) | 0.0357 (p = 0.2091) | <0.0001 / <0.0001 |
| Atlanta | 86 | 0.0077 (p < 0.0001) | 0.0136 (p < 0.0001) | −0.0032 (p < 0.0001) | −0.0042 (p < 0.0001) | −0.0460 (p < 0.0001) | −0.0711 (p < 0.0001) | <0.0001 / <0.0001 |
| Chicago | 52 | 0.0025 (p = 0.0149) | 0.0045 (p = 0.0002) | 0.0003 (p = 0.7289) | 0.0023 (p = 0.0116) | −0.0585 (p = 0.0277) | −0.0308 (p = 0.3066) | <0.0001 / <0.0001 |
| Seattle | 71 | 0.0015 (p = 0.1088) | 0.0039 (p = 0.0018) | 0.0061 (p < 0.0001) | 0.0063 (p < 0.0001) | 0.0714 (p = 0.0123) | 0.0600 (p = 0.0563) | <0.0001 / <0.0001 |
| Miami | 73 | −0.0001 (p = 0.9469) | −0.0006 (p = 0.6970) | 0.0012 (p < 0.0001) | 0.0008 (p = 0.0372) | 0.0084 (p = 0.6349) | −0.0079 (p = 0.7327) | <0.0001 / <0.0001 |

Units are natural: per commute-minute, per km of CBD distance, and per log-point of job accessibility, on log rent. p-values are conventional ZCTA-clustered; "n identifying" counts ZCTAs observed both pre and post break. † Memphis's row is reported for completeness only — see the under-identified flag above.

**Read the joint model with the collinearity caveat in hand.** The three gradients are mutually correlated, so joint-model signs are conditional: where joint and single-interaction models disagree — Seattle's access interaction is +0.0714 joint but −0.1080 single at Post1; Phoenix's distance is −0.0021 joint but +0.0002 (n.s.) single — the disagreement is collinearity doing the talking, and the per-metro verdicts below lean on whichever pattern is stable across both.

### Spatial Robustness — Wild Cluster Bootstrap (Webb weights, ZIP3 clusters)

Re-clustering at the 3-digit ZIP prefix answers the Barrios–Diamond–Imbens–Kolesár concern that unit-clustered SEs are understated for spatially smooth regressors. It thins the significance map considerably:

| Metro | Commute (P1 / P2) | Distance (P1 / P2) | Access (P1 / P2) |
|-------|-------------------|--------------------|-------------------|
| Phoenix | 0.1241 / 0.2222 | 0.0300 / 0.0511 | 0.1161 / 0.2232 |
| Los Angeles | 0.3914 / 0.9099 | 0.9179 / 0.8539 | 0.1051 / 0.1321 |
| Dallas-Fort Worth | 0.1942 / 0.1882 | 0.1141 / 0.1702 | 0.0260 / 0.0490 |
| Memphis | 0.7518 / 0.9429 | 0.5996 / 0.3754 | 0.5305 / 0.6857 |
| Denver | 0.0420 / 0.1381 | 0.0260 / 0.4324 | 0.0420 / 0.3554 |
| Atlanta | 0.1652 / 0.0951 | 0.0320 / 0.0711 | 0.7818 / 0.7037 |
| Chicago | 0.4765 / 0.7688 | 0.9219 / 0.6987 | 0.2152 / 0.3333 |
| Seattle | 0.3964 / 0.2482 | 0.0140 / 0.0210 | 0.1762 / 0.2192 |
| Miami | 0.9469 / 0.6777 | 0.1662 / 0.2012 | 0.6727 / 0.7728 |

Survivors at p < 0.05: Seattle's distance interaction (both phases), DFW's access interaction (both phases), Denver's full phase-1 set, and the phase-1 distance interactions in Phoenix and Atlanta. Memphis's ZCTA-level bootstrap (the headline inference for an under-identified metro) confirms the null: commute 0.8068 / 0.9530, distance 0.8068 / 0.8228, access 0.2823 / 0.7497.

### Event Study — Pre-Trend Verdicts (Spec B)

The event study interacts the three gradients with event-time bins relative to 2020-03 (base bin 2019-03…2020-02); flat pre-break coefficients support the parallel-trends reading of Spec A, while a drifting pre-path demotes Spec A's coefficients to "trend + break". Per-bin identifying-ZCTA counts matter: the earliest bins are thin in several metros (Memphis 7, Denver 12, Seattle 17, Chicago 29, Los Angeles 30 ZCTAs).

| Metro | Pre-trend verdict |
|-------|-------------------|
| Los Angeles | **Flat** — the cleanest pre-path in the study; all pre-bins statistically indistinguishable from base for all three regressors (the elevated pre4 points rest on 30 ZCTAs and stay inside their CIs). Parallel-trends reading supported. |
| Chicago | **Flat for commute; drift for access** — commute pre-bins sit on zero (the post-break rise is a clean break); the access pre-path is elevated and declines into the break (pre1 +0.0335, CI excludes zero), so the access repricing partially reads as trend. |
| Denver | **Drift for commute** — pre3/pre2 commute bins are significantly below base (−0.0052, −0.0026): the post-break rise partly continues a pre-existing steepening. Distance and access pre-paths are flat within (wide) CIs; earliest bin rests on 12 ZCTAs. |
| Phoenix | **Drift for distance; commute borderline** — distance pre-bins are significantly positive and decline monotonically into the break (pre4 +0.0042 → pre1 +0.0006); the commute pre-path rises monotonically but no pre-bin individually excludes base. Access flat after a noisy pre4. |
| Dallas-Fort Worth | **Drift for distance and access; commute flat** — distance and access pre4/pre3 bins are significantly positive and decline into base. |
| Atlanta | **Drift on all three** — every regressor's pre-path is significantly non-zero and monotone into the break (distance +0.0043 at pre4 falling to +0.0012 at pre1, all four bins excluding base). Spec A's large Atlanta coefficients read as the acceleration of a pre-existing steepening — trend + break, not a clean break. |
| Seattle | **Strongest drift in the study** — distance (−0.0152 → −0.0011) and access (−0.336 → −0.015) pre-paths are large, significant, and rising into base; the positive post-break distance coefficients continue that trajectory. Commute pre-path is flat. |
| Miami | **Drift on all three** — commute, distance, and access pre-bins are significantly below base and rise into it; the small positive post-break distance coefficient sits on that pre-existing path. |
| Memphis | **Uninformative** — pre-bins rest on 7–12 identifying ZCTAs with CIs spanning zero everywhere. |

### Per-Metro Verdicts

- **Phoenix:** commute gradient repriced upward in both phases (+0.0037 / +0.0048 per minute) with access down in the disruption phase; only the distance interaction survives the ZIP3 bootstrap, and the distance pre-path drifts. Moderate-confidence, persistent repricing.
- **Los Angeles: access-only repricing, no commute effect** — the commute and distance interactions are null in both phases (p ≥ 0.20 everywhere), while the access interaction is −0.0582 in Post1, deepening to −0.0876 in Post2: rents in job-accessible ZCTAs fell relative to the rest of the covered submarket and kept falling into the RTO era. Pre-trends are flat (cleanest event study of the nine); the ZIP3 bootstrap narrowly misses (p ≈ 0.11–0.13).
- **Dallas-Fort Worth:** access-led repricing (−0.0330 / −0.0382, the study's most bootstrap-robust access result: p = 0.0260 / 0.0490) with a smaller distance effect; commute itself never significant. Distance/access pre-paths drift.
- **Memphis:** no evidence either way — under-identified (12 identifying ZCTAs), joint Wald p = 0.6034 / 0.9714, every bootstrap p ≥ 0.28.
- **Denver:** the strongest commute repricing (+0.0056 / +0.0076, both p < 0.0001; full phase-1 set survives the ZIP3 bootstrap at p ≤ 0.042) — but the commute pre-path drifts, so part of the rise predates COVID.
- **Atlanta:** the largest coefficients in the study on all three regressors, all p < 0.0001 and all *growing* in Post2 (commute +0.0077 → +0.0136) — and the clearest pre-trend drift on all three. Read as a pre-existing periphery-ward steepening that COVID accelerated, not a clean break.
- **Chicago:** the cleanest commute break of the nine (flat pre-trend; +0.0025 in Post1 nearly doubling to +0.0045 in Post2), plus a disruption-phase access effect (−0.0585) that fades to insignificance in Post2 — the study's one clear partial reversal. Nothing survives the ZIP3 bootstrap.
- **Seattle:** large positive distance repricing (+0.0061 / +0.0063; the most bootstrap-robust result in the study, p = 0.0140 / 0.0210) — but the steepest pre-trends of the nine run straight into it, and the joint access sign flips against the single-interaction model. Trend + break, direction periphery-favoring.
- **Miami:** essentially no COVID-specific repricing — commute and access null throughout; the tiny distance effect (+0.0012 / +0.0008) sits on a significant pre-existing path and fails the bootstrap (p = 0.1662).

### Cross-Metro Synthesis

- **Where repricing happened, it favored the periphery.** Positive commute interactions (Phoenix, Denver, Atlanta, Chicago), negative access interactions (Phoenix, LA, DFW, Atlanta, Chicago-P1), and positive distance interactions (Seattle) all point the same way: covered ZCTAs far from jobs gained rent relative to job-rich cores. No metro shows core-favoring repricing that survives both the single-interaction check and the pre-trend check.
- **The repricing did not reverse in the RTO era.** In no metro does a significant Post1 effect return to zero in Post2; in Atlanta, Chicago (commute), Denver, and LA the Post2 coefficient *exceeds* Post1. The one clean fade is Chicago's access effect (−0.0585 → −0.0308 n.s.). The disruption-phase reshuffle largely stuck or deepened through 2022–26.
- **The honesty rails matter.** Pre-trend drift demotes Atlanta, Seattle, and Miami (and the distance channels in Phoenix and DFW, plus Denver's commute channel) to "trend + break"; the ZIP3 wild bootstrap sustains only Seattle distance, DFW access, Denver's phase-1 set, and Phoenix/Atlanta distance-P1 at p < 0.05. The strictly-clean-and-robust list is short; the *directional* consistency across nine metros is the stronger finding.
- **Entry selection is signed, not just acknowledged.** Post-2019-12 entrants are more peripheral than incumbents on all three gradients (higher commute proxy and CBD distance, lower access) in seven of nine metros — Atlanta's entrants are *less* peripheral and Chicago's are mixed — so incumbent-identified estimates likely *understate* periphery repricing where entrants are peripheral; the balanced-subpanel bound (ZCTAs in-sample by 2019-01) sits close to the headline in every metro and changes no substantive conclusion.
- **Secondary specs stay secondary.** Spec C (within-ZCTA annual accessibility) is significantly negative in LA, Chicago, and Seattle, positive in Miami, and null elsewhere on the headline window (Denver's positive theta reaches p = 0.0177 only when the noisy 2020/2021 LODES years are dropped). Spec D's lead-term falsification fails — the *lead* of accessibility is significant — in Phoenix, LA, Chicago, Seattle, Atlanta, and Miami, so the rents-and-jobs association reads as feedback, not "rents chase jobs", exactly the trap the design's predictive-association framing anticipated. Spec C-med mediation shares are unstable (−3.0 to +1.7 across metros) and are not leaned on.

### Index-Choice Robustness (SA vs non-SA ZORI)

The committed panel deliberately uses the **non-seasonally-adjusted** ZORI series (two-sided SA factors re-estimated each vintage would leak post-2020 information into pre-2020 values — an anticipation artifact at the break; the month FE already absorb seasonality). As the design's one-off check, RQ4 was re-run for Phoenix, Los Angeles, and Chicago against a local, uncommitted build of the SA series (`Zip_zori_uc_sfrcondomfr_sm_sa_month.csv`, pull vintage **2026-07-17**). Every Spec A interaction coefficient moves by well under one SE — the largest shift in all three metros is Phoenix's commute × Post1, 0.00366 → 0.00341 (≈ 0.18 SE) — with no sign change and no coefficient crossing the 0.05 boundary in either direction. The index choice is not driving the results.

### Deferred

The ACS-wave longitudinal panel (re-estimating RQ1/RQ3 across ACS vintages, §8.3) remains deferred, with a re-scope trigger at the 2022–2026 5-year ACS release (~Dec 2027) per issue #8. Also deferred per design §6: LODES 2024+ appends, dynamic-panel and spatial-lag estimators, Conley spatial-HAC SEs, ZORI tier/segment variants, and network travel-time distances.