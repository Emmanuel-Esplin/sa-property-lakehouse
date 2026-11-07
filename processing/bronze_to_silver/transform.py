"""Bronze to silver: the existing parsers and contracts, handed to Spark.

Reusing them means local and cloud runs apply one set of rules, not two that can drift apart.
"""

import pandas as pd
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import DateType, DoubleType, StringType, StructField, StructType

RETAIL_SCHEMA = StructType(
    [
        StructField("month", DateType(), False),
        StructField("category", StringType(), False),
        StructField("price_basis", StringType(), False),
        StructField("adjustment", StringType(), False),
        StructField("value_rmillion", DoubleType(), False),
    ]
)
CPI_SCHEMA = StructType(
    [
        StructField("month", DateType(), False),
        StructField("cpi_yoy_pct", DoubleType(), False),
    ]
)


def to_spark(spark: SparkSession, frame: pd.DataFrame, schema: StructType) -> DataFrame:
    """Convert via plain tuples, so the pandas version here and on Glue doesn't matter."""
    columns = [field.name for field in schema.fields]
    rows = [
        tuple(float(value) if isinstance(value, int | float) else value for value in row)
        for row in frame[columns].itertuples(index=False, name=None)
    ]
    return spark.createDataFrame(rows, schema)


def latest_key(client, bucket: str, prefix: str) -> str:
    """Return the most recently stored object, because bronze keeps every vintage."""
    pages = client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
    objects = [item for page in pages for item in page.get("Contents", [])]
    if not objects:
        raise FileNotFoundError(f"Nothing in s3://{bucket}/{prefix}")
    return max(objects, key=lambda item: item["LastModified"])["Key"]
