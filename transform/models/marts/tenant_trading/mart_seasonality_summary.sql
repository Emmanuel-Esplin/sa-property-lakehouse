select
    s.category,
    c.label,
    c.segment,
    max_by(s.month_of_year, s.seasonal_index) as peak_month,
    max(s.seasonal_index) as peak_index,
    min_by(s.month_of_year, s.seasonal_index) as trough_month,
    min(s.seasonal_index) as trough_index,
    max(s.seasonal_index) - min(s.seasonal_index) as seasonal_amplitude,
    max(s.years_used) as years_used
from {{ ref('mart_seasonality_monthly') }} as s
inner join {{ ref('retail_categories') }} as c on c.category = s.category
group by s.category, c.label, c.segment
