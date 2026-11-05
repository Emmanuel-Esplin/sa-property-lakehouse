create or replace table stg_retail as
select month::date as month, category, price_basis, adjustment, value_rmillion
from read_parquet(getvariable('silver_dir') || '/retail_trade.parquet');

create or replace table stg_cpi as
select month::date as month, cpi_yoy_pct
from read_parquet(getvariable('silver_dir') || '/cpi.parquet');

create or replace table dim_retail_category as
select * from read_csv(getvariable('seed_dir') || '/retail_categories.csv', header = true);
