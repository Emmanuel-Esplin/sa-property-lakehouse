-- Monthly interest rates, the benchmark for REIT dividend yields.
-- Policy and prime rates move in steps, so the month-end value is the rate in force.
-- The bond yield moves every day, so it is averaged over the month.
with daily as (
    select
        cast(date_trunc('month', rate_date) as date) as month,
        rate_date,
        series,
        value_pct
    from {{ ref('stg_rates') }}
),
monthly as (
    select
        month,
        max_by(value_pct, rate_date) filter (where series = 'repo_rate') as repo_rate_pct,
        max_by(value_pct, rate_date) filter (where series = 'prime_rate') as prime_rate_pct,
        avg(value_pct) filter (where series = 'govt_bond_10y_plus') as bond_10y_plus_yield_pct
    from daily
    group by month
),
-- Months run from the first one every series covers to the last one that has ended.
-- The repo series starts two days before the others, and the latest month's average would
-- cover only part of it.
coverage as (
    select max(first_month) as first_month
    from (select series, min(month) as first_month from daily group by series) as starts
),
complete as (
    select monthly.*
    from monthly
    cross join coverage
    where monthly.month >= coverage.first_month
        and monthly.month < (select max(month) from monthly)
)
select
    m.month,
    m.repo_rate_pct,
    m.prime_rate_pct,
    m.bond_10y_plus_yield_pct,
    m.repo_rate_pct - prev.repo_rate_pct as repo_change_pts,
    c.cpi_yoy_pct,
    -- Uses inflation over the past year, not expected inflation, so it is an approximation.
    m.bond_10y_plus_yield_pct - c.cpi_yoy_pct as real_bond_yield_pct
from complete as m
left join complete as prev
    on prev.month = cast({{ dbt.dateadd('month', -1, 'm.month') }} as date)
left join {{ ref('stg_cpi') }} as c on c.month = m.month
