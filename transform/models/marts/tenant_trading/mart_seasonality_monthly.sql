-- Seasonal index: a month's share of its year, scaled so 1.0 is an average month.
-- Uses up to the five latest complete years, skipping 2020-2021, when lockdowns distorted the
-- normal pattern.
with complete_years as (
    select category, year(month) as yr
    from {{ ref('int_retail_monthly') }}
    where year(month) not in (2020, 2021)
    group by category, year(month)
    having count(*) = 12
),
ranked_years as (
    select category, yr, row_number() over (partition by category order by yr desc) as recency
    from complete_years
),
indexed as (
    select
        m.category,
        month(m.month) as month_of_year,
        m.real_rmillion / (sum(m.real_rmillion) over (partition by m.category, r.yr) / 12)
            as seasonal_index
    from {{ ref('int_retail_monthly') }} as m
    inner join ranked_years as r
        on r.category = m.category and r.yr = year(m.month) and r.recency <= 5
)
select category, month_of_year, avg(seasonal_index) as seasonal_index, count(*) as years_used
from indexed
group by category, month_of_year
