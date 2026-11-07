-- Unadjusted figures: comparing a month with the same month a year earlier already removes
-- seasonality, and the seasonality mart needs the seasonal pattern left in.
select
    month,
    category,
    max(value_rmillion) filter (where price_basis = 'current') as nominal_rmillion,
    max(value_rmillion) filter (where price_basis = 'constant') as real_rmillion
from {{ ref('stg_retail') }}
where adjustment = 'unadjusted'
group by month, category
