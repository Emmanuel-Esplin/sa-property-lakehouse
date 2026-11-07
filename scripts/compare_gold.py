"""Compare exported marts, for example from Athena, with the local DuckDB marts, row by row.

Usage: compare_gold.py <folder holding one folder of Parquet files per mart>
"""

import math
import sys
from pathlib import Path

import duckdb

from ingestion.common.bronze import data_dir

KEYS = {
    "mart_tenant_growth": ["month", "category"],
    "mart_tenant_scorecard": ["category"],
    "mart_segment_scorecard": ["segment"],
    "mart_seasonality_monthly": ["category", "month_of_year"],
    "mart_seasonality_summary": ["category"],
    "mart_rates_monthly": ["month"],
    "mart_reit_monthly": ["month", "ticker"],
    "mart_reit_returns": ["ticker"],
    "mart_sector_rate_sensitivity": ["sector"],
}
TOLERANCE = 1e-6


def parquet_files(folder: Path) -> list[str]:
    """Data files in an export folder. Athena names them without an extension, and Spark adds
    marker files such as _SUCCESS, so neither a name pattern nor "every file" works."""
    files = sorted(
        str(path)
        for path in folder.iterdir()
        if path.is_file() and not path.name.startswith(("_", "."))
    )
    if not files:
        raise FileNotFoundError(f"No exported data files in {folder}")
    return files


def same(left, right) -> bool:
    """Equal, allowing for float rounding. Engines add up floats in different orders."""
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, int | float) and isinstance(right, int | float):
        return math.isclose(left, right, abs_tol=TOLERANCE)
    return left == right


def compare_mart(connection, name: str, keys: list[str], folder: Path) -> list[str]:
    """Every difference between the exported mart and the local one, as readable lines."""
    order = ", ".join(keys)
    # Both sides are read with the same sorted column list, so column order can't matter.
    header = connection.execute(f"select * from warehouse.{name} limit 0").description
    columns = sorted(column[0] for column in header)
    select = ", ".join(columns)
    expected_rows = connection.execute(
        f"select {select} from warehouse.{name} order by {order}"
    ).fetchall()
    files = parquet_files(folder / name)
    actual = connection.execute("select * from read_parquet(?) limit 0", [files]).description
    if sorted(column[0] for column in actual) != columns:
        return [f"{name}: columns differ"]
    actual_rows = connection.execute(
        f"select {select} from read_parquet(?) order by {order}", [files]
    ).fetchall()
    if len(actual_rows) != len(expected_rows):
        return [f"{name}: {len(actual_rows)} rows, expected {len(expected_rows)}"]
    differences = []
    for expected_row, actual_row in zip(expected_rows, actual_rows, strict=True):
        for column, left, right in zip(columns, expected_row, actual_row, strict=True):
            if not same(left, right):
                differences.append(f"{name}.{column}: {right} vs {left}")
    return differences


def main(folder: Path) -> int:
    """Compare every mart, print a line each, and return 1 if anything differs."""
    warehouse = data_dir() / "gold" / "warehouse.duckdb"
    failures = compared = 0
    with duckdb.connect() as connection:
        connection.execute(f"attach '{warehouse}' as warehouse (read_only)")
        for name, keys in KEYS.items():
            differences = compare_mart(connection, name, keys, folder)
            rows = connection.execute(f"select count(*) from warehouse.{name}").fetchone()[0]
            compared += rows
            failures += len(differences)
            print(f"{name}: {rows} rows, {len(differences)} differences")
            for difference in differences[:5]:
                print(f"  {difference}")
    print(f"Compared {compared} rows: {failures} differences")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
