"""Build the gold layer: run the SQL in order, check it, and export the marts to Parquet."""

from pathlib import Path

import duckdb

from ingestion.common.bronze import data_dir

TRANSFORM_DIR = Path(__file__).parent
MARTS = [
    "mart_tenant_growth",
    "mart_tenant_scorecard",
    "mart_segment_scorecard",
    "mart_seasonality_monthly",
    "mart_seasonality_summary",
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


def build(root: Path) -> Path:
    silver = root / "silver"
    for name in ("retail_trade.parquet", "cpi.parquet"):
        if not (silver / name).exists():
            raise FileNotFoundError(f"Missing {silver / name}. Run `make cpi` and `make retail`.")

    gold = root / "gold"
    gold.mkdir(parents=True, exist_ok=True)
    warehouse = gold / "warehouse.duckdb"
    with duckdb.connect(str(warehouse)) as connection:
        connection.execute("set variable silver_dir = ?", [str(silver)])
        connection.execute("set variable seed_dir = ?", [str(TRANSFORM_DIR / "seeds")])
        for script in sorted((TRANSFORM_DIR / "sql").glob("*.sql")):
            connection.execute(script.read_text())

        failures = {
            name: rows
            for name, query in CHECKS.items()
            if (rows := connection.sql(query).fetchall())
        }
        if failures:
            summary = "; ".join(f"{name} ({len(rows)})" for name, rows in failures.items())
            raise ValueError(f"Gold checks failed: {summary}")

        for mart in MARTS:
            target = gold / f"{mart}.parquet"
            connection.execute(f"copy {mart} to '{target}' (format parquet)")
    return warehouse


if __name__ == "__main__":
    print(f"Built {build(data_dir())}")
