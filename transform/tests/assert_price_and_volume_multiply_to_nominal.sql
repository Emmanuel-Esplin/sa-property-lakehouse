select month, category
from {{ ref('mart_tenant_growth') }}
where abs((1 + real_yoy_pct / 100) * (1 + price_yoy_pct / 100) - (1 + nominal_yoy_pct / 100))
    > 1e-9
