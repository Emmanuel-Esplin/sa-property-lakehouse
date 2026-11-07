-- An index of 1.0 is an average month, so the twelve months must average exactly 1.
select category
from {{ ref('mart_seasonality_monthly') }}
group by category
having abs(avg(seasonal_index) - 1) > 1e-9
