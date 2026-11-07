{% if target.type == 'duckdb' %}
select month::date as month, cpi_yoy_pct
from read_parquet('{{ var("silver_dir") }}/cpi.parquet')
{% else %}
select month, cpi_yoy_pct
from {{ source('silver', 'silver_cpi') }}
{% endif %}
