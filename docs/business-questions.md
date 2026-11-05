# Business questions

Each question maps to a mart. "Planned" means nothing has been built for it yet.

## Module 2: tenant trading

| Question | Answered by | Method |
|---|---|---|
| How has turnover grown over 24 months, by retailer type? | `mart_tenant_growth` | Unadjusted sales against the same month a year earlier |
| How much growth is real, and how much is price? | `mart_tenant_growth` | Constant-price growth is volume. Price is the exact remainder: `(1 + nominal) / (1 + real) - 1` |
| Which categories grow above CPI? | `mart_tenant_scorecard.above_cpi` | Nominal growth over the latest 12 months against the 12 before, compared with average CPI |
| Which categories shrink in real terms? | `mart_tenant_scorecard.shrinking_in_real_terms` | Constant-price growth below zero on the same windows |
| Which categories are most seasonal? | `mart_seasonality_summary` | Peak-to-trough range of each month's share of its year, in constant prices |
| How do defensive and discretionary categories compare? | `mart_segment_scorecard`, and the `segment` column in each mart | Category mapping in `transform/seeds/retail_categories.csv` |
| Does retail growth lead or lag REIT share prices? | Planned, Phase 5 | Needs the REIT module |

"Above CPI" and "shrinking in real terms" can disagree, and both are reported. The first compares
sales with general inflation. The second removes the category's own price change. A category whose
prices rise faster than CPI can beat CPI while selling less.

## Module 1: REIT market performance (planned)

- How have SA REIT dividend yields moved relative to the prime rate and the 10-year government bond?
- Which REIT sectors are most sensitive to repo rate changes?
- What are inflation-adjusted total returns per REIT over 3 and 5 years?
