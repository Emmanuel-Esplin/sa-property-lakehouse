select category
from {{ ref('mart_seasonality_monthly') }}
group by category
having abs(avg(seasonal_index) - 1) > 1e-9
