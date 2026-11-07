-- Annualised total returns over 3 and 5 years, before and after inflation.
-- Every REIT is measured to the same month: the latest one that both prices and CPI cover.
with as_at as (
    select least(
        (select max(month) from {{ ref('mart_reit_monthly') }}),
        (select max(month) from {{ ref('stg_cpi') }})
    ) as month
),
monthly as (
    select
        m.*,
        {{ dbt.datediff('m.month', 'a.month', 'month') }} as months_back
    from {{ ref('mart_reit_monthly') }} as m
    cross join as_at as a
),
growth as (
    -- Compounding is a product of (1 + return), taken as exp(sum(ln)) so it works as a sum.
    select
        ticker,
        max(name) as name,
        max(sector) as sector,
        count(total_return_pct) filter (where months_back between 0 and 35) as months_3y,
        exp(sum(ln(1 + total_return_pct / 100)) filter (where months_back between 0 and 35))
            as growth_3y,
        count(total_return_pct) filter (where months_back between 0 and 59) as months_5y,
        exp(sum(ln(1 + total_return_pct / 100)) filter (where months_back between 0 and 59))
            as growth_5y
    from monthly
    group by ticker
),
inflation as (
    -- Year-on-year CPI at the as-at month and at 12, 24... months before chains exactly into
    -- inflation over 3 or 5 whole years.
    select
        count(*) filter (where months_back in (0, 12, 24)) as cpi_years_3y,
        exp(sum(ln(1 + cpi_yoy_pct / 100)) filter (where months_back in (0, 12, 24)))
            as inflation_3y,
        count(*) filter (where months_back in (0, 12, 24, 36, 48)) as cpi_years_5y,
        exp(sum(ln(1 + cpi_yoy_pct / 100)) filter (where months_back in (0, 12, 24, 36, 48)))
            as inflation_5y
    from (
        select c.cpi_yoy_pct, {{ dbt.datediff('c.month', 'a.month', 'month') }} as months_back
        from {{ ref('stg_cpi') }} as c
        cross join as_at as a
    ) as cpi
)
select
    g.ticker,
    g.name,
    g.sector,
    a.month as as_at_month,
    -- A return is only shown when every month of its window is there.
    case when g.months_3y = 36 then 100 * (power(g.growth_3y, cast(1 as double) / 3) - 1) end
        as annual_return_3y_pct,
    case
        when g.months_3y = 36 and i.cpi_years_3y = 3
            then 100 * (power(g.growth_3y / i.inflation_3y, cast(1 as double) / 3) - 1)
    end as real_annual_return_3y_pct,
    case when g.months_5y = 60 then 100 * (power(g.growth_5y, cast(1 as double) / 5) - 1) end
        as annual_return_5y_pct,
    case
        when g.months_5y = 60 and i.cpi_years_5y = 5
            then 100 * (power(g.growth_5y / i.inflation_5y, cast(1 as double) / 5) - 1)
    end as real_annual_return_5y_pct
from growth as g
cross join as_at as a
cross join inflation as i
