# Cross-Metro Findings: Housing Affordability & Commute Trade-Off Analysis

**Date:** 2026-03-07
**Revised:** 2026-07 (employment variables)
**Metros Analyzed:** Atlanta (ATL), Chicago (CHI), Dallas-Fort Worth (DFW), Denver (DEN), Los Angeles (LA), Memphis (MEM), Miami (MIA), Phoenix (PHX), Seattle (SEA)

---

## Executive Summary

This analysis examines the relationship between housing affordability, commute time, and transit access across nine U.S. metropolitan areas at the ZCTA level. The central finding is that **affordability is primarily an income and renter-concentration problem** — renter share is a significant predictor of rent burden in 8 of 9 metros, while commute time is significant in 6 of 9 (revised up from 4 of 9 after the 2026-07 addition of employment-center variables; see §9). Racial disparities in housing cost burden are pervasive (8 of 9 metros), and transit access signals expensive, high-demand areas in dense cities; no metro shows a significant affordability-serving transit effect once employment structure is controlled.

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
- **The concave relationship** persists in Denver, DFW, and Memphis, indicating a "drive until you qualify" effect with diminishing returns: rent burden gains flatten at longer commutes. Miami flipped from concave to positive linear; Seattle's selected model is now a convex quadratic, but its commute terms are not significant.
- **Multicollinearity increased with the new variables**: `job_accessibility` posts VIFs of 5–11 in every metro except DFW, and Los Angeles — formerly the only metro with no multicollinearity issues (max VIF = 3.38) — now has a max VIF of 9.21.

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

The concave quadratic relationships in Denver, DFW, and Memphis (Miami's re-run model is now positive linear) show that rent burden initially decreases with longer commutes but plateaus. At a certain distance, further driving no longer buys proportionally more affordability — suggesting a spatial boundary to the tradeoff.

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
5. **Examine the "drive until you qualify" threshold.** The concave relationships suggest a spatial boundary where commute-affordability tradeoffs break down. Identifying this inflection point per metro could inform housing location guidance.

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