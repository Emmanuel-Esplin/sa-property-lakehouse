"""Build the Spark marts from local silver files, to compare with the DuckDB marts."""

import os
import sys
from pathlib import Path

from pyspark.sql import SparkSession

from ingestion.common.bronze import data_dir
from processing.silver_to_gold.marts import build_marts


def local_session() -> SparkSession:
    # Otherwise workers use whichever python3 is on PATH, which may be another version.
    os.environ["PYSPARK_PYTHON"] = sys.executable
    return (
        SparkSession.builder.master("local[2]")
        .appName("lakehouse-local")
        .config("spark.driver.host", "localhost")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )


def write_local_marts(spark: SparkSession, silver: Path, target: Path) -> None:
    spark.read.parquet(str(silver / "retail_trade.parquet")).createOrReplaceTempView("stg_retail")
    spark.read.parquet(str(silver / "cpi.parquet")).createOrReplaceTempView("stg_cpi")
    for name, frame in build_marts(spark).items():
        frame.coalesce(1).write.mode("overwrite").parquet(str(target / name))


if __name__ == "__main__":
    root = data_dir()
    output = root / "spark_gold"
    session = local_session()
    write_local_marts(session, root / "silver", output)
    session.stop()
    print(f"Wrote {output}", file=sys.stdout)
