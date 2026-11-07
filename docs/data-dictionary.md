# Data dictionary

## Silver

### `retail_trade.parquet`

One row per month, category, price basis and adjustment.

| Column | Type | Description |
| --- | --- | --- |
| `month` | date | First day of the month |
| `category` | string | Retailer type slug, listed in `transform/seeds/retail_categories.csv` |
| `price_basis` | string | `current` or `constant` (2019 prices as of the August 2026 release) |
| `adjustment` | string | `unadjusted` or `seasonally_adjusted` |
| `value_rmillion` | double | Sales in R million |

### `cpi.parquet`

| Column | Type | Description |
| --- | --- | --- |
| `month` | date | First day of the month |
| `cpi_yoy_pct` | double | Headline CPI, all urban areas, year-on-year %. Published to one decimal |

### `rates.parquet`

One row per business day and series, as SARB publishes them.

| Column | Type | Description |
| --- | --- | --- |
| `rate_date` | date | The business day |
| `series` | string | `repo_rate` (SARB policy rate), `prime_rate`, or `govt_bond_10y_plus` |
| `value_pct` | double | The rate or yield, in % |

### `reit_prices.parquet` and `reit_distributions.parquet`

From the CSV files described in [market-data-format.md](market-data-format.md). Empty until files
are landed.

| Column | Type | Description |
| --- | --- | --- |
| `price_date` | date | A trading day (prices) |
| `ex_date` | date | The ex-date (distributions) |
| `ticker` | string | JSE ticker, listed in `transform/seeds/reits.csv` |
| `close_cents` | double | Closing price in cents (prices) |
| `amount_cents` | double | Distribution per share in cents (distributions) |

On AWS, these are the Iceberg tables `silver_retail_trade`, `silver_cpi` and `silver_rates` in the
Glue database `sa_property_lakehouse`. The REIT files aren't on AWS yet.

## Gold

dbt builds these. On AWS, each mart is an Iceberg table of the same name in the Glue database
`sa_property_lakehouse_marts`.

### `mart_tenant_growth`

One row per month and category.

| Column | Description |
| --- | --- |
| `month`, `category`, `label`, `segment` | Keys and category descriptions |
| `nominal_rmillion`, `real_rmillion` | Unadjusted sales at current and constant prices |
| `nominal_yoy_pct`, `real_yoy_pct` | Growth on the same month a year earlier. NULL for the first year |
| `price_yoy_pct` | Implied price growth, `(1 + nominal) / (1 + real) - 1` |
| `cpi_yoy_pct` | Headline CPI for the month |
| `nominal_minus_cpi_pts` | Nominal growth minus CPI, in percentage points |

### `mart_tenant_scorecard`

One row per category, as at the latest month. Windows are the latest 12 months and the 12 before.

| Column | Description |
| --- | --- |
| `category`, `label`, `segment`, `latest_month` | Keys and the as-at month |
| `nominal_growth_pct`, `real_growth_pct`, `price_growth_pct` | Growth between the two windows |
| `avg_cpi_yoy_pct` | Average headline CPI over the latest 12 months |
| `above_cpi` | Nominal growth is above that average |
| `shrinking_in_real_terms` | Constant-price growth is below zero |
| `months_above_cpi_last_24` | Months of the last 24 where nominal growth beat CPI |
| `months_real_decline_last_24` | Months of the last 24 where real growth was negative |

### `mart_segment_scorecard`

One row per segment, using the same windows. Categories are added together, so large ones weigh more.

| Column | Description |
| --- | --- |
| `segment` | `defensive`, `discretionary` or `mixed` |
| `nominal_growth_pct`, `real_growth_pct`, `price_growth_pct` | Growth between the two windows |

### `mart_seasonality_monthly`

One row per category and calendar month.

| Column | Description |
| --- | --- |
| `category`, `month_of_year` | Keys. `month_of_year` runs from 1 to 12 |
| `seasonal_index` | Constant-price sales against an average month of the same year, averaged across years. 1.0 is an average month |
| `years_used` | Number of complete years in the average |

### `mart_seasonality_summary`

One row per category.

| Column | Description |
| --- | --- |
| `category`, `label`, `segment` | Keys and category descriptions |
| `peak_month`, `peak_index` | Strongest calendar month and its index |
| `trough_month`, `trough_index` | Weakest calendar month and its index |
| `seasonal_amplitude` | Peak index minus trough index. Larger means more seasonal |
| `years_used` | Number of complete years in the average |

### `mart_rates_monthly`

One row per month, from the first month every rate series covers to the last month that has ended.

| Column | Description |
| --- | --- |
| `month` | First day of the month |
| `repo_rate_pct`, `prime_rate_pct` | Rates in force at month end. They move in steps, so this is the rate that applied |
| `bond_10y_plus_yield_pct` | Average daily yield on government bonds of 10 years and longer |
| `repo_change_pts` | Change in the policy rate from the previous month end, in percentage points |
| `cpi_yoy_pct` | Headline CPI for the month. NULL until SARB publishes it |
| `real_bond_yield_pct` | Bond yield minus CPI. It uses past inflation, not expected inflation, so it's approximate |

### `mart_reit_monthly`

One row per REIT and month.

| Column | Description |
| --- | --- |
| `month`, `ticker`, `name`, `sector` | Keys and the REIT's details from the seed |
| `close_cents`, `distribution_cents` | Month-end price, and distributions that went ex in the month |
| `price_return_pct`, `total_return_pct` | Change from the previous month end, without and with distributions |
| `distribution_yield_pct` | Last 12 months of distributions over the month-end price. NULL until 12 months exist |
| `prime_rate_pct`, `bond_10y_plus_yield_pct`, `repo_change_pts` | From `mart_rates_monthly` |
| `yield_spread_to_bond_pts`, `yield_spread_to_prime_pts` | Distribution yield minus each rate |

### `mart_reit_returns`

One row per REIT, as at the latest month that both prices and CPI cover.

| Column | Description |
| --- | --- |
| `ticker`, `name`, `sector`, `as_at_month` | Keys and the end of the measurement window |
| `annual_return_3y_pct`, `annual_return_5y_pct` | Annualised total return. NULL unless every month in the window has one |
| `real_annual_return_3y_pct`, `real_annual_return_5y_pct` | The same, after CPI over the same years |

### `mart_sector_rate_sensitivity`

One row per sector. A sector's monthly return is the equal-weighted average of its REITs.

| Column | Description |
| --- | --- |
| `sector` | From the seed |
| `months`, `hike_months`, `cut_months` | Months with a return, and how many had a policy rate rise or fall |
| `avg_return_hike_months_pct`, `avg_return_cut_months_pct`, `avg_return_hold_months_pct` | Average monthly total return in each kind of month |
| `return_per_rate_point_pct` | Fitted change in a month's return per 1-point policy rate change |
