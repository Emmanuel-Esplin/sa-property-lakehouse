# Business questions

Each question maps to a mart. "Planned" means nothing has been built for it yet.

## Module 2: tenant trading

| Question | Answered by | Method |
| --- | --- | --- |
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

## Module 1: REIT market performance (in progress)

The marts are built and tested. They fill once REIT price and distribution files are landed,
in the format described in [market-data-format.md](market-data-format.md).

| Question | Answered by | Method |
| --- | --- | --- |
| How have SA REIT dividend yields moved relative to prime and the long government bond? | `mart_reit_monthly` | Trailing 12-month distributions over month-end price, against prime and the bond yield |
| Which REIT sectors are most sensitive to repo rate changes? | `mart_sector_rate_sensitivity` | Each sector's average return in hike, cut and hold months, and the fitted return per rate point |
| What are inflation-adjusted total returns per REIT over 3 and 5 years? | `mart_reit_returns` | Monthly total returns compounded and annualised, then CPI over the same years removed |

The bond benchmark is SARB's average yield on government bonds of 10 years and longer, series
`CMJD004A`. It is published daily from 2002, which single bonds such as the R2030 are not.
