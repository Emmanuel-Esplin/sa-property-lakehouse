-- Same-category, same-month growth, split into volume (real) and price.
-- Joined on the date, not LAG, so a missing month gives NULL instead of the wrong comparison.
with growth as (
    select
        cur.month,
        cur.category,
        cur.nominal_rmillion,
        cur.real_rmillion,
        cur.nominal_rmillion / prev.nominal_rmillion - 1 as nominal_growth,
        cur.real_rmillion / prev.real_rmillion - 1 as real_growth
    from {{ ref('int_retail_monthly') }} as cur
    left join {{ ref('int_retail_monthly') }} as prev
        on prev.category = cur.category
        and prev.month = cast({{ dbt.dateadd('month', -12, 'cur.month') }} as date)
)
select
    g.month,
    g.category,
    c.label,
    c.segment,
    g.nominal_rmillion,
    g.real_rmillion,
    100 * g.nominal_growth as nominal_yoy_pct,
    100 * g.real_growth as real_yoy_pct,
    -- Exact identity: (1 + nominal) = (1 + real) * (1 + price).
    100 * ((1 + g.nominal_growth) / (1 + g.real_growth) - 1) as price_yoy_pct,
    p.cpi_yoy_pct,
    100 * g.nominal_growth - p.cpi_yoy_pct as nominal_minus_cpi_pts
from growth as g
inner join {{ ref('retail_categories') }} as c on c.category = g.category
left join {{ ref('stg_cpi') }} as p on p.month = g.month
