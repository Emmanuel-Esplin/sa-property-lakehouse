-- A growth figure without CPI would silently drop out of the "beat CPI" comparison.
select month, category
from {{ ref('mart_tenant_growth') }}
where cpi_yoy_pct is null and nominal_yoy_pct is not null
