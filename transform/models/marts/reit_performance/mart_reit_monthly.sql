-- Monthly returns and distribution yield for each REIT, beside the rates they compete with.
with monthly_returns as (
    select
        cur.*,
        100 * (cur.close_cents / prev.close_cents - 1) as price_return_pct,
        -- A distribution counts in the month it goes ex, as if received at that month's end.
        100 * ((cur.close_cents + cur.distribution_cents) / prev.close_cents - 1)
            as total_return_pct
    from {{ ref('int_reit_monthly') }} as cur
    left join {{ ref('int_reit_monthly') }} as prev
        on prev.ticker = cur.ticker
        and prev.month = cast({{ dbt.dateadd('month', -1, 'cur.month') }} as date)
),
twelve_month_totals as (
    -- Prices have no gaps, so twelve rows back is always twelve months back.
    select
        *,
        sum(distribution_cents) over (
            partition by ticker order by month rows between 11 preceding and current row
        ) as distributions_t12_cents,
        count(*) over (
            partition by ticker order by month rows between 11 preceding and current row
        ) as months_in_window
    from monthly_returns
),
yields as (
    select
        *,
        case
            when months_in_window = 12 then 100 * distributions_t12_cents / close_cents
        end as distribution_yield_pct
    from twelve_month_totals
)
select
    y.month,
    y.ticker,
    y.name,
    y.sector,
    y.close_cents,
    y.distribution_cents,
    y.price_return_pct,
    y.total_return_pct,
    y.distribution_yield_pct,
    r.prime_rate_pct,
    r.bond_10y_plus_yield_pct,
    r.repo_change_pts,
    y.distribution_yield_pct - r.bond_10y_plus_yield_pct as yield_spread_to_bond_pts,
    y.distribution_yield_pct - r.prime_rate_pct as yield_spread_to_prime_pts
from yields as y
left join {{ ref('mart_rates_monthly') }} as r on r.month = y.month
