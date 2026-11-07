-- Daily REIT closing prices from silver: Parquet locally, the Iceberg table on Athena.
{% if target.type == 'duckdb' %}
select price_date::date as price_date, ticker, close_cents
from read_parquet('{{ var("silver_dir") }}/reit_prices.parquet')
{% else %}
select price_date, ticker, close_cents
from {{ source('silver', 'silver_reit_prices') }}
{% endif %}
