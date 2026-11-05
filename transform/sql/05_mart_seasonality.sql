-- Seasonal index: a month's share of its year, scaled so 1.0 is an average month.
-- Uses complete years only, skipping 2020-2021, when lockdowns distorted the normal pattern.
create or replace table mart_seasonality_monthly as
with complete_years as (
    select category, year(month) as yr
    from int_retail_monthly
    where year(month) not in (2020, 2021)
    group by category, year(month)
    having count(*) = 12
),
recent_years as (
    select category, yr
    from complete_years
    qualify row_number() over (partition by category order by yr desc) <= 5
),
indexed as (
    select
        m.category,
        month(m.month) as month_of_year,
        m.real_rmillion / (sum(m.real_rmillion) over (partition by m.category, r.yr) / 12)
            as seasonal_index
    from int_retail_monthly as m
    inner join recent_years as r
        on r.category = m.category and r.yr = year(m.month)
)
select category, month_of_year, avg(seasonal_index) as seasonal_index, count(*) as years_used
from indexed
group by category, month_of_year;

create or replace table mart_seasonality_summary as
select
    s.category,
    c.label,
    c.segment,
    arg_max(s.month_of_year, s.seasonal_index) as peak_month,
    max(s.seasonal_index) as peak_index,
    arg_min(s.month_of_year, s.seasonal_index) as trough_month,
    min(s.seasonal_index) as trough_index,
    max(s.seasonal_index) - min(s.seasonal_index) as seasonal_amplitude,
    any_value(s.years_used) as years_used
from mart_seasonality_monthly as s
inner join dim_retail_category as c using (category)
group by s.category, c.label, c.segment;
