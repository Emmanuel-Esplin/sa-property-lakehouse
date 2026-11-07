-- Daily SARB rates from silver: Parquet locally, the Iceberg table on Athena.
{% if target.type == 'duckdb' %}
select rate_date::date as rate_date, series, value_pct
from read_parquet('{{ var("silver_dir") }}/rates.parquet')
{% else %}
select rate_date, series, value_pct
from {{ source('silver', 'silver_rates') }}
{% endif %}
