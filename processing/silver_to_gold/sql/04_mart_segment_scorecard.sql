-- The same 12-month windows, with categories added together into each segment.
create or replace temporary view mart_segment_scorecard as
with latest as (
    select max(month) as latest_month from int_retail_monthly
),
windowed as (
    select
        c.segment,
        m.nominal_rmillion,
        m.real_rmillion,
        cast(months_between(l.latest_month, m.month) as int) as months_ago
    from int_retail_monthly as m
    inner join dim_retail_category as c on c.category = m.category
    cross join latest as l
    where c.segment <> 'total'
),
summary as (
    select
        segment,
        sum(nominal_rmillion) filter (where months_ago < 12) as nominal_t12,
        sum(nominal_rmillion) filter (where months_ago between 12 and 23) as nominal_p12,
        sum(real_rmillion) filter (where months_ago < 12) as real_t12,
        sum(real_rmillion) filter (where months_ago between 12 and 23) as real_p12
    from windowed
    group by segment
)
select
    segment,
    100 * (nominal_t12 / nominal_p12 - 1) as nominal_growth_pct,
    100 * (real_t12 / real_p12 - 1) as real_growth_pct,
    100 * ((nominal_t12 / nominal_p12) / (real_t12 / real_p12) - 1) as price_growth_pct
from summary
