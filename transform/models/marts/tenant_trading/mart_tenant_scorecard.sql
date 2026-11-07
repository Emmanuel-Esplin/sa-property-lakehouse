-- Latest 12 months against the 12 before them, which is steadier than any single month.
with latest as (
    select max(month) as latest_month from {{ ref('mart_tenant_growth') }}
),
windowed as (
    select
        g.*,
        l.latest_month,
        {{ dbt.datediff('g.month', 'l.latest_month', 'month') }} as months_ago
    from {{ ref('mart_tenant_growth') }} as g
    cross join latest as l
),
summary as (
    select
        category,
        max(label) as label,
        max(segment) as segment,
        max(latest_month) as latest_month,
        sum(nominal_rmillion) filter (where months_ago < 12) as nominal_t12,
        sum(nominal_rmillion) filter (where months_ago between 12 and 23) as nominal_p12,
        sum(real_rmillion) filter (where months_ago < 12) as real_t12,
        sum(real_rmillion) filter (where months_ago between 12 and 23) as real_p12,
        count(*) filter (where months_ago < 12) as months_t12,
        count(*) filter (where months_ago between 12 and 23) as months_p12,
        avg(cpi_yoy_pct) filter (where months_ago < 12) as avg_cpi_yoy_pct,
        count(cpi_yoy_pct) filter (where months_ago < 12) as cpi_months_t12,
        count(*) filter (where months_ago < 24 and nominal_yoy_pct > cpi_yoy_pct)
            as months_above_cpi_last_24,
        count(*) filter (where months_ago < 24 and real_yoy_pct < 0)
            as months_real_decline_last_24
    from windowed
    group by category
),
scored as (
    select
        *,
        100 * (nominal_t12 / nominal_p12 - 1) as nominal_growth_pct,
        100 * (real_t12 / real_p12 - 1) as real_growth_pct
    from summary
    where months_t12 = 12 and months_p12 = 12
)
select
    category,
    label,
    segment,
    latest_month,
    nominal_growth_pct,
    real_growth_pct,
    100 * ((1 + nominal_growth_pct / 100) / (1 + real_growth_pct / 100) - 1) as price_growth_pct,
    case when cpi_months_t12 = 12 then avg_cpi_yoy_pct end as avg_cpi_yoy_pct,
    case when cpi_months_t12 = 12 then nominal_growth_pct > avg_cpi_yoy_pct end as above_cpi,
    real_growth_pct < 0 as shrinking_in_real_terms,
    months_above_cpi_last_24,
    months_real_decline_last_24
from scored
