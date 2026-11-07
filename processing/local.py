"""A local Spark session for tests."""

import os
import sys

from pyspark.sql import SparkSession


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
