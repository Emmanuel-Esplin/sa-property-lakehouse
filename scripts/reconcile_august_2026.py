"""Compare the marts with growth rates Stats SA published in the August 2026 P6242.1 release.

The figures below are copied from Tables 2, 5 and 12 of that PDF. Stats SA revises history, so
differences are expected once the warehouse is built from a later release.

Usage: reconcile_august_2026.py [folder of exported marts, to check instead of the warehouse]
"""

import sys
from pathlib import Path

import duckdb

from ingestion.common.bronze import data_dir
from scripts.compare_gold import parquet_files

MONTHS = ["2026-03-01", "2026-04-01", "2026-05-01", "2026-06-01", "2026-07-01", "2026-08-01"]
TABLE_5_REAL = {
    "general_dealers": [1.7, 1.0, 0.9, 1.5, 3.3, 2.0],
    "food_beverages_tobacco": [-5.5, -0.3, -0.2, 2.6, 5.0, 5.8],
    "pharma_cosmetics": [5.0, 0.6, 1.8, 1.5, 2.4, 2.1],
    "textiles_clothing_footwear": [3.9, -1.0, 3.9, -4.1, 2.9, 6.5],
    "household_furniture_appliances": [10.8, 8.6, 7.6, 8.7, 6.3, 3.0],
    "hardware_paint_glass": [0.3, 0.1, -0.5, -4.0, -1.1, -3.6],
    "other_retailers": [7.2, 4.8, 6.4, 7.3, 6.4, 8.1],
    "total": [2.5, 1.2, 2.2, 1.1, 3.4, 3.3],
}
TABLE_12_NOMINAL = {
    "general_dealers": [4.1, 3.3, 2.8, 3.3, 4.9, 3.7],
    "food_beverages_tobacco": [1.5, 5.2, 3.6, 5.3, 6.0, 7.2],
    "pharma_cosmetics": [7.7, 3.2, 4.2, 3.8, 4.8, 4.3],
    "textiles_clothing_footwear": [4.3, -0.5, 4.3, -3.6, 3.5, 7.2],
    "household_furniture_appliances": [6.3, 4.5, 3.1, 4.6, 4.2, 1.5],
    "hardware_paint_glass": [2.0, 2.1, 2.1, -0.6, 2.3, 0.1],
    "other_retailers": [5.7, 3.5, 5.5, 6.9, 5.9, 7.6],
    "total": [4.2, 2.8, 3.4, 2.6, 4.6, 4.5],
}
TABLE_2_ANNUAL_REAL = {2021: 6.2, 2022: 1.3, 2023: -1.5, 2024: 2.5, 2025: 3.7}


def _connect() -> duckdb.DuckDBPyConnection:
    if len(sys.argv) > 1:
        connection = duckdb.connect()
        files = parquet_files(Path(sys.argv[1]) / "mart_tenant_growth")
        rows = connection.read_parquet(files)
        connection.register("mart_tenant_growth", rows)
        return connection
    return duckdb.connect(str(data_dir() / "gold" / "warehouse.duckdb"), read_only=True)


def main() -> int:
    failures = compared = 0
    with _connect() as connection:
        for column, table in (
            ("real_yoy_pct", TABLE_5_REAL),
            ("nominal_yoy_pct", TABLE_12_NOMINAL),
        ):
            for category, values in table.items():
                for month, published in zip(MONTHS, values, strict=True):
                    mine = connection.execute(
                        f"select {column} from mart_tenant_growth where category = ? and month = ?",
                        [category, month],
                    ).fetchone()[0]
                    compared += 1
                    if round(mine, 1) != published:
                        failures += 1
                        print(f"{column} {category} {month}: {mine:.2f} vs {published}")
        for year, published in TABLE_2_ANNUAL_REAL.items():
            mine = connection.execute(
                """select 100 * (sum(real_rmillion) filter (year(month) = ?)
                                 / sum(real_rmillion) filter (year(month) = ?) - 1)
                   from mart_tenant_growth where category = 'total'""",
                [year, year - 1],
            ).fetchone()[0]
            compared += 1
            if round(mine, 1) != published:
                failures += 1
                print(f"annual {year}: {mine:.2f} vs {published}")
    print(f"Compared {compared} published figures: {failures} differ at one decimal place")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
