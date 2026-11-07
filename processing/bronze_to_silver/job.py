"""Glue job: parse the latest bronze files and write validated silver Iceberg tables."""

import tempfile
from pathlib import Path

import boto3

from ingestion.sarb.cpi import parse_cpi
from ingestion.stats_sa.retail_trade import parse_release, validate_retail
from processing.bronze_to_silver.transform import CPI_SCHEMA, RETAIL_SCHEMA, latest_key, to_spark
from processing.lake import glue_session, job_argument, table


def main() -> None:
    bucket = job_argument("LAKE_BUCKET")
    client = boto3.client("s3")
    spark = glue_session(bucket, "bronze-to-silver")

    retail_key = latest_key(client, bucket, "bronze/stats_sa/retail_trade/")
    with tempfile.TemporaryDirectory() as folder:
        workbook = Path(folder) / "release.xlsx"
        client.download_file(bucket, retail_key, str(workbook))
        retail = validate_retail(parse_release(workbook))

    cpi_key = latest_key(client, bucket, "bronze/sarb/cpi/")
    cpi = parse_cpi(client.get_object(Bucket=bucket, Key=cpi_key)["Body"].read())

    to_spark(spark, retail, RETAIL_SCHEMA).writeTo(table("silver_retail_trade")).using(
        "iceberg"
    ).createOrReplace()
    to_spark(spark, cpi, CPI_SCHEMA).writeTo(table("silver_cpi")).using("iceberg").createOrReplace()

    print(f"SILVER retail={len(retail)} from {retail_key}; cpi={len(cpi)} from {cpi_key}")
    spark.stop()


if __name__ == "__main__":
    main()
