# Findings: how South Africa's retail tenants are trading

Stats SA's retail trade sales, release P6242.1, up to August 2026, and SARB interest rates up to
October 2026. "Growth" compares the latest 12 months, September 2025 to August 2026, with the 12
months before. Every figure comes from the project's dbt marts. Run `make dashboard` to see them as
charts.

## Summary

Retail sales grew 4.3%, ahead of CPI at 3.8%. Most of that growth, 2.6 points, was volume. A
landlord whose rent includes a share of turnover would have seen it rise slightly faster than
inflation.

Averages hide the split. **Defensive retailers grew on price and discretionary ones on volume**, so
the tenants that look strongest on turnover aren't always the ones gaining shoppers.

## 1. Most retailer types beat inflation, two didn't

| Retailer type | Sales growth | Beat CPI (3.8%)? | Months above CPI, last 24 |
| --- | ---: | --- | ---: |
| Pharmacy and cosmetics | 6.5% | Yes | 18 |
| All other retailers | 5.8% | Yes | 14 |
| Specialist food and drink | 5.1% | Yes | 14 |
| Furniture and appliances | 4.7% | Yes | 18 |
| General dealers | 4.0% | Yes, by 0.2 points | 17 |
| Clothing and footwear | 3.4% | No, by 0.4 points | 15 |
| Hardware, paint and glass | 2.3% | No | 8 |
| **All retailers** | **4.3%** | **Yes** | **21** |

General dealers and clothing sit within half a point of CPI. Stats SA revises recent months, so
either could change sides.

## 2. Volume and price tell different stories

| Retailer type | Volume | Implied price |
| --- | ---: | ---: |
| Furniture and appliances | 8.9% | -3.8% |
| All other retailers | 7.4% | -1.5% |
| Pharmacy and cosmetics | 3.5% | 3.0% |
| Clothing and footwear | 2.9% | 0.5% |
| General dealers | 1.7% | 2.3% |
| Hardware, paint and glass | 0.7% | 1.6% |
| Specialist food and drink | **-1.1%** | 6.3% |

- **Specialist food and drink beat CPI while selling less.** Volume fell in 14 of the last 24
  months, and prices carried all of the growth. Turnover rent is holding up, but the tenant's
  shoppers are buying less.
- **Furniture and appliances gained the most volume.** Its volume grew 8.9%, the most of any type, but
  falling prices cut its sales growth to 4.7%.
- **By segment,** defensive retailers grew volume 1.5% on sales growth of 4.5%. Discretionary
  retailers grew volume 3.2% on sales growth of 3.3%.

## 3. Hardware is the weakest tenant type

Hardware, paint and glass had the lowest sales growth, 2.3%. It beat CPI in only 8 of the last 24
months, and its volume fell year on year in 12 of them, including each of the last four.

## 4. Clothing depends on December

At constant prices, an average month is 1.00. December is:

| Retailer type | December | Quietest month |
| --- | ---: | --- |
| Clothing and footwear | 1.80 | September, 0.83 |
| Furniture and appliances | 1.41 | January, 0.87 |
| Specialist food and drink | 1.41 | June, 0.92 |
| General dealers | 1.30 | January, 0.89 |
| Pharmacy and cosmetics | 1.08 | February, 0.93 |

A clothing tenant does almost twice an average month's trade in December. A weak festive season
moves its year far more than a pharmacy's. Hardware is the one type that peaks in November, at 1.14.

## 5. Rates are rising again

- **Repo:** the policy rate peaked at 8.25% from May 2023 to August 2024. Cuts took it to 6.75% by
  November 2025. Two rises, in May and September 2026, have taken it back to 7.25%. Prime follows
  3.5 points above it, at 10.75%.
- **Bond yields:** the yield on government bonds of 10 years and longer fell from 12.4% in October
  2023 to 8.9% in September 2026.
- **Real bond yield:** with CPI at 4.5%, that is a real yield of about 4.4%.

Property yields are usually priced against long bond yields, so the fall since 2023 eases pressure
on valuations. The 2026 repo rises push the cost of floating-rate debt back up, while tenant sales
growth is only just ahead of inflation.

## What this data can't show

- **Not tenant turnover.** These are national sales by retailer type, not turnover for any
  landlord's tenants. Growth includes store openings and closures, so it isn't like-for-like.
  Use it as a benchmark for a portfolio's own tenant sales.
- **"Implied price" is a residual.** It is the part of sales growth that volume doesn't explain:
  `(1 + nominal) / (1 + real) - 1`. It isn't a measured price index.
- **CPI is broader than retail.** It covers services as well as goods, so beating CPI is a
  benchmark, not a like-for-like price comparison.
- **Recent months are preliminary.** Stats SA revises them in later releases.

## How the figures are checked

- **Against Stats SA:** all 101 growth rates in Stats SA's August 2026 release match the marts at
  one decimal place. Run `make reconcile` to repeat the check.
- **Across engines:** the same marts built on AWS match the local build on all 2,205 rows.
- **Within the marts:** dbt tests check each step on every build, for example that no month is
  missing and that prime stays 3.5 points above repo.
