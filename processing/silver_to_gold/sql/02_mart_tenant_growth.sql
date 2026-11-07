-- Same-category, same-month growth, split into volume (real) and price.
-- Joined on the date, not LAG, so a missing month gives NULL instead of the wrong comparison.
create or replace temporary view mart_tenant_growth as
with growth as (
    select
        cur.month,
        cur.category,
        cur.nominal_rmillion,
        cur.real_rmillion,
        cur.nominal_rmillion / prev.nominal_rmillion - 1 as nominal_growth,
        cur.real_rmillion / prev.real_rmillion - 1 as real_growth
    from int_retail_monthly as cur
    left join int_retail_monthly as prev
        on prev.category = cur.category
        and prev.month = add_months(cur.month, -12)
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
    100 * ((1 + g.nominal_growth) / (1 + g.real_growth) - 1) as price_yoy_pct,
    p.cpi_yoy_pct,
    100 * g.nominal_growth - p.cpi_yoy_pct as nominal_minus_cpi_pts
from growth as g
inner join dim_retail_category as c on c.category = g.category
left join stg_cpi as p on p.month = g.month
