-- REIT distributions per share, dated by ex-date: Parquet locally, the Iceberg table on Athena.
{% if target.type == 'duckdb' %}
select ex_date::date as ex_date, ticker, amount_cents
from read_parquet('{{ var("silver_dir") }}/reit_distributions.parquet')
{% else %}
select ex_date, ticker, amount_cents
from {{ source('silver', 'silver_reit_distributions') }}
{% endif %}
