"""Shared Spark and Iceberg settings for the Glue jobs."""

import sys

from pyspark.sql import SparkSession

CATALOG = "glue_catalog"
DATABASE = "sa_property_lakehouse"


def job_argument(name: str) -> str:
    """Read a `--NAME value` argument, the way Glue passes job parameters."""
    return sys.argv[sys.argv.index(f"--{name}") + 1]


def table(name: str) -> str:
    """The full Iceberg name for a table in this project's Glue database."""
    return f"{CATALOG}.{DATABASE}.{name}"


def glue_session(bucket: str, app_name: str) -> SparkSession:
    """Start Spark with Iceberg tables stored in S3 and registered in the Glue catalog."""
    catalog = f"spark.sql.catalog.{CATALOG}"
    return (
        SparkSession.builder.appName(app_name)
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config(catalog, "org.apache.iceberg.spark.SparkCatalog")
        .config(f"{catalog}.warehouse", f"s3://{bucket}/warehouse/")
        .config(f"{catalog}.catalog-impl", "org.apache.iceberg.aws.glue.GlueCatalog")
        .config(f"{catalog}.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
        .getOrCreate()
    )
