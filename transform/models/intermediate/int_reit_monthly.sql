-- Month-end price and the month's distributions for each REIT.
-- The latest month is left out until it ends, so a part-month never looks like a full one.
with prices as (
    select
        cast(date_trunc('month', price_date) as date) as month,
        ticker,
        price_date,
        close_cents
    from {{ ref('stg_reit_prices') }}
),
month_end as (
    select month, ticker, max_by(close_cents, price_date) as close_cents
    from prices
    group by month, ticker
),
distributions as (
    select month, ticker, sum(amount_cents) as distribution_cents
    from (
        select cast(date_trunc('month', ex_date) as date) as month, ticker, amount_cents
        from {{ ref('stg_reit_distributions') }}
    ) as dated
    group by month, ticker
)
select
    m.month,
    m.ticker,
    r.name,
    r.sector,
    m.close_cents,
    coalesce(d.distribution_cents, 0) as distribution_cents
from month_end as m
inner join {{ ref('reits') }} as r on r.ticker = m.ticker
left join distributions as d on d.month = m.month and d.ticker = m.ticker
where m.month < (select max(month) from month_end)
