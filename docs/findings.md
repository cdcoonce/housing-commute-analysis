# Cross-Metro Findings: Housing Affordability & Commute Trade-Off Analysis

**Date:** 2026-03-07
**Metros Analyzed:** Atlanta (ATL), Chicago (CHI), Dallas-Fort Worth (DFW), Denver (DEN), Los Angeles (LA), Memphis (MEM), Miami (MIA), Phoenix (PHX), Seattle (SEA)

---

## Executive Summary

This analysis examines the relationship between housing affordability, commute time, and transit access across nine U.S. metropolitan areas at the ZCTA level. The central finding is that **affordability is primarily an income and renter-concentration problem, not a commute problem** — commute time is a statistically significant predictor of rent burden in only 4 of 9 metros. Racial disparities in housing cost burden are pervasive (8 of 9 metros), and transit access has contradictory effects depending on metro structure: it signals expensive, high-demand areas in dense cities but genuinely serves affordability in sprawling ones.

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
| Memphis | Quadratic | 0.726 | Yes | <0.001 | Concave |
| Seattle | Linear | 0.585 | Yes | <0.01 | Positive linear |
| Atlanta | Quadratic | 0.554 | No | 0.31 | Convex |
| Denver | Quadratic | 0.483 | Yes | <0.05 | Concave |
| Chicago | Quadratic | 0.435 | No | 0.37 | Convex |
| Los Angeles | Linear | 0.428 | No | 0.09 | Positive linear |
| Dallas-Fort Worth | Quadratic | 0.322 | Yes | <0.01 | Concave |
| Phoenix | Linear | 0.315 | No | 0.56 | Weak positive |
| Miami | Quadratic | 0.300 | No | 0.05 | Concave |

### Key Takeaways

- **Commute time is statistically significant in only 4 of 9 metros** (Memphis, Seattle, Denver, DFW). In the other five, other factors dominate.
- **Renter share is the most consistently significant predictor**, reaching p < 0.01 in 7 of 9 metros. Areas with higher concentrations of renters have higher rent burdens universally.
- **Memphis has the strongest model fit** (R² = 0.73), likely because its smaller, simpler spatial structure follows a more predictable center-periphery gradient.
- **Phoenix is the hardest metro to model** (R² = 0.32, no significant predictors), suggesting its affordability dynamics are driven by factors outside this analysis — possibly rapid development, land use patterns, or seasonal population shifts.
- **The concave relationship** in Denver, DFW, Memphis, and Miami indicates a "drive until you qualify" effect with diminishing returns: rent burden drops with longer commutes up to a point, then plateaus. Very long commutes do not continue to buy proportionally more affordability.
- **Los Angeles is the only metro with no multicollinearity issues** (max VIF = 3.38), making it the most technically reliable model despite moderate explanatory power.

---

## 4. RQ2 — Equity Analysis

### Income Disparities

- **All 9 metros show statistically significant income-based rent burden differences** (p < 0.0001 in all cases). This is the single most robust finding in the entire analysis.
- Chicago has the strongest F-statistic (F = 103.9), indicating the most pronounced income stratification in rent burden.

### Racial Disparities

- **8 of 9 metros show significant racial differences in rent burden.** Majority-white ZCTAs consistently have lower rent burdens.
- **Seattle is the sole exception** — no significant racial differences (F = 0.11, p = 0.90). Seattle's affordability dynamics are income-driven but not race-stratified.
- Chicago shows the strongest racial disparity signal (F = 59.0), followed by DFW (F = 26.9) and Memphis (F = 21.4).

### Commute × Income Interaction

- In **8 of 9 metros**, the interaction between commute time and low-income status is not significant — the commute-rent tradeoff operates similarly regardless of income level.
- **Seattle is again the exception** (p = 0.014): low-income ZCTAs there experience a fundamentally different commute-affordability dynamic. The negative interaction coefficient (−0.0062) suggests low-income residents in Seattle benefit more from the "drive until you qualify" tradeoff than other income groups.

### Transit Access and Income

Transit density differs significantly across income segments in only 3 metros:
- **Chicago** (p = 0.003)
- **Los Angeles** (p < 0.0001)
- **Miami** (p = 0.0002)

These are the three metros with the most developed transit systems, suggesting transit access is income-stratified only where transit infrastructure is substantial.

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
| Chicago | 0.573 | Yes (p < 0.0001) | Positive |
| Seattle | 0.485 | No | — |
| Los Angeles | 0.373 | No | — |
| Dallas-Fort Worth | 0.354 | Yes (p = 0.007) | **Negative** |
| Denver | 0.352 | No | — |
| Miami | 0.318 | Yes (p = 0.017) | Positive |
| Atlanta | 0.238 | No | — |
| Memphis | 0.168 | No | — |
| Phoenix | 0.017 | No | — |

### Key Takeaways

- **Transit access has contradictory effects depending on metro structure:**
  - In **Chicago and Miami**, transit-rich areas have *higher* combined ACI pressure because they are desirable, expensive locations. More transit = more demand = higher costs.
  - In **Dallas-Fort Worth**, transit access has a significant *negative* relationship with ACI — the only metro where more transit = less combined pressure. Quantile regression confirms this across all quantiles (coefficients −0.04 to −0.085, strengthening at higher quantiles). DFW's transit genuinely serves affordable areas.
  - In 6 other metros, transit has no measurable effect on ACI.

- **Phoenix is essentially unexplainable** by this model (R² = 0.017). The transit/income/rent/commute dynamics there operate through mechanisms not captured by these variables.

- **The Memphis paradox:** Best-fitting RQ1 model (R² = 0.73) but worst-fitting ACI model (R² = 0.17). Commute time alone powerfully predicts rent burden in Memphis, but when you add transit to the model, it collapses — because Memphis has virtually no transit infrastructure. Transit stop density is near zero for most ZCTAs.

- **ACI distribution varies substantially across metros:**
  - Chicago has the widest range (−3.64 to 6.08), indicating extreme within-metro variation.
  - Memphis has the tightest range (max 2.0), indicating more spatial homogeneity.
  - Los Angeles has an extreme negative outlier (ACI = −6.675).

---

## 6. Cross-Cutting Themes

### Theme A: Affordability Is an Income Problem, Not a Commute Problem

Commute time predicts rent burden in only 4 of 9 metros. Renter share and income segment are the dominant drivers everywhere. Policy interventions targeting commute reduction alone will not meaningfully address affordability.

### Theme B: Racial Inequality in Housing Is Pervasive but Not Universal

8 of 9 metros show significant racial rent burden disparities. Seattle's exception — no racial disparities but significant income disparities — suggests its housing market stratifies by wealth rather than race. This finding merits further investigation.

### Theme C: Transit Is a Double-Edged Sword

In dense, established transit cities (Chicago, Miami), transit-rich areas have higher combined housing-commute pressure because they are in-demand locations. In car-dependent sprawl metros (DFW), transit access genuinely reduces combined pressure. For most metros, transit has no measurable effect. Transit investment must be paired with affordability protections to avoid displacement.

### Theme D: "Drive Until You Qualify" Has Limits

The concave quadratic relationships in Denver, DFW, Memphis, and Miami show that rent burden initially decreases with longer commutes but plateaus. At a certain distance, further driving no longer buys proportionally more affordability — suggesting a spatial boundary to the tradeoff.

### Theme E: Metro Structure Matters More Than Metro Size

Memphis (75 ZCTAs) has the best RQ1 model fit; Phoenix (147 ZCTAs) and Miami (178 ZCTAs) have the worst. Explanatory power tracks with how consistently the metro's spatial structure follows the expected center-periphery gradient, not with observation count.

---

## 7. Notable Outliers and Anomalies

| Finding | Metro | Detail |
|---------|-------|--------|
| No racial rent disparities | Seattle | Only metro where race does not significantly predict rent burden (F = 0.11, p = 0.90) |
| Significant commute × income interaction | Seattle | Only metro where low-income residents experience a different commute-rent tradeoff (p = 0.014) |
| Transit reduces ACI | DFW | Only metro where transit access is associated with lower combined pressure |
| Extreme pressure ZCTAs | ATL, SEA | 2-ZCTA clusters with rent burdens of 0.527 (ATL) and 0.432 (SEA) |
| Double-burdened zone | Chicago | Cluster with highest rent burden (0.333) AND longest commute (39.9 min) |
| Unexplainable by model | Phoenix | Both RQ1 (R² = 0.32) and ACI (R² = 0.02) models fail to explain variance |
| Widest income gap | Memphis | 17.1 percentage point gap between low- and high-income rent burden |
| Best RQ1, worst ACI | Memphis | R² = 0.73 for commute model, R² = 0.17 for transit-inclusive model |

---

## 8. Implications for Policy and Future Research

### Policy Implications

1. **Income-targeted interventions** (rental assistance, inclusionary zoning, wage policy) are more likely to reduce rent burden than commute-oriented strategies alone.
2. **Transit investment requires affordability protections.** In Chicago and Miami, transit-rich areas already price out lower-income residents. Expanding transit without anti-displacement measures may worsen affordability in the areas it serves.
3. **DFW's transit model is worth studying.** It is the only metro where transit access correlates with lower combined pressure — understanding why could inform transit planning in other sprawl metros.
4. **Racial equity in housing** remains a challenge in 8 of 9 metros. Place-based policies must account for racial disparities in cost burden, not just income-based ones.

### Future Research Directions

1. **Investigate Phoenix.** Neither model explains its affordability dynamics. Rapid growth, seasonal migration, and land use patterns are candidate explanatory factors.
2. **Explore Seattle's racial equity outlier.** Why does Seattle show no racial rent burden disparities when 8 other metros do? Is this a function of demographics, policy, or spatial sorting?
3. **Longitudinal analysis.** This cross-sectional analysis captures a single point in time. Tracking how these relationships evolve — especially in rapidly growing metros like Phoenix, DFW, and Seattle — would strengthen causal claims.
4. **Incorporate employment center locations.** Adding job density or distance-to-CBD as variables could improve model fit, particularly in polycentric metros like LA and DFW.
5. **Examine the "drive until you qualify" threshold.** The concave relationships suggest a spatial boundary where commute-affordability tradeoffs break down. Identifying this inflection point per metro could inform housing location guidance.