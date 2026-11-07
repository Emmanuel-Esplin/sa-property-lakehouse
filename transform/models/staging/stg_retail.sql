-- Retail sales from silver: Parquet locally, the Iceberg table on Athena.
{% if target.type == 'duckdb' %}
select month::date as month, category, price_basis, adjustment, value_rmillion
from read_parquet('{{ var("silver_dir") }}/retail_trade.parquet')
{% else %}
select month, category, price_basis, adjustment, value_rmillion
from {{ source('silver', 'silver_retail_trade') }}
{% endif %}
