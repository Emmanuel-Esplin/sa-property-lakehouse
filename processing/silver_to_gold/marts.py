"""Silver to gold in Spark SQL. Expects `stg_retail` and `stg_cpi` to exist as views."""

import csv
import io
import pkgutil

from pyspark.sql import DataFrame, SparkSession

MARTS = [
    "mart_tenant_growth",
    "mart_tenant_scorecard",
    "mart_segment_scorecard",
    "mart_seasonality_monthly",
    "mart_seasonality_summary",
]
# pkgutil reads these from a folder locally and from the zip on Glue, so the list is explicit.
SQL_FILES = [
    "01_int_retail_monthly.sql",
    "02_mart_tenant_growth.sql",
    "03_mart_tenant_scorecard.sql",
    "04_mart_segment_scorecard.sql",
    "05_mart_seasonality_monthly.sql",
    "06_mart_seasonality_summary.sql",
]
# Each query must return no rows.
CHECKS = {
    "retail categories missing from the seed": """
        select distinct category from stg_retail
        where category not in (select category from dim_retail_category)
    """,
    "retail months with no CPI": """
        select month from mart_tenant_growth
        where cpi_yoy_pct is null and nominal_yoy_pct is not null
    """,
    "price and volume growth do not multiply to nominal growth": """
        select month, category from mart_tenant_growth
        where abs((1 + real_yoy_pct / 100) * (1 + price_yoy_pct / 100)
                  - (1 + nominal_yoy_pct / 100)) > 1e-9
    """,
    "seasonal index does not average 1": """
        select category from mart_seasonality_monthly
        group by category having abs(avg(seasonal_index) - 1) > 1e-9
    """,
}


def load_categories(spark: SparkSession) -> None:
    raw = pkgutil.get_data("transform", "seeds/retail_categories.csv").decode()
    rows = [tuple(row.values()) for row in csv.DictReader(io.StringIO(raw))]
    spark.createDataFrame(
        rows, "category string, label string, segment string"
    ).createOrReplaceTempView("dim_retail_category")


def build_marts(spark: SparkSession) -> dict[str, DataFrame]:
    """Build every mart and run the checks, raising if any check finds rows."""
    load_categories(spark)
    for name in SQL_FILES:
        spark.sql(pkgutil.get_data(__package__, f"sql/{name}").decode())

    failures = {
        name: count for name, query in CHECKS.items() if (count := spark.sql(query).count())
    }
    if failures:
        summary = "; ".join(f"{name} ({count})" for name, count in failures.items())
        raise ValueError(f"Gold checks failed: {summary}")
    return {name: spark.table(name) for name in MARTS}
