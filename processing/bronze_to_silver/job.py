"""Glue job: parse the latest bronze files and write validated silver Iceberg tables."""

import tempfile
from pathlib import Path

import boto3
import pandas as pd

from ingestion.sarb.cpi import parse_cpi
from ingestion.sarb.rates import parse_rates
from ingestion.sarb.series import CPI, RATES
from ingestion.stats_sa.retail_trade import parse_release, validate_retail
from processing.bronze_to_silver.transform import (
    CPI_SCHEMA,
    RATES_SCHEMA,
    RETAIL_SCHEMA,
    latest_key,
    to_spark,
)
from processing.lake import glue_session, job_argument, table


def read_retail(client, bucket: str) -> pd.DataFrame:
    """The latest workbook, parsed and validated by the same code as the local pipeline."""
    key = latest_key(client, bucket, "bronze/stats_sa/retail_trade/")
    # openpyxl reads from a file, so the workbook is downloaded rather than streamed.
    with tempfile.TemporaryDirectory() as folder:
        workbook = Path(folder) / "release.xlsx"
        client.download_file(bucket, key, str(workbook))
        return validate_retail(parse_release(workbook))


def read_sarb(client, bucket: str, dataset: str) -> bytes:
    """The latest stored response for one SARB series."""
    key = latest_key(client, bucket, f"bronze/sarb/{dataset}/")
    return client.get_object(Bucket=bucket, Key=key)["Body"].read()


def main() -> None:
    """Read the latest bronze files, then replace the three silver tables."""
    bucket = job_argument("LAKE_BUCKET")
    client = boto3.client("s3")
    spark = glue_session(bucket, "bronze-to-silver")

    retail = read_retail(client, bucket)
    cpi = parse_cpi(read_sarb(client, bucket, CPI.dataset))
    rates = pd.concat(
        [parse_rates(series, read_sarb(client, bucket, series.dataset)) for series in RATES],
        ignore_index=True,
    )

    # Parse everything before writing anything, so one bad source leaves silver unchanged.
    for name, frame, schema in (
        ("silver_retail_trade", retail, RETAIL_SCHEMA),
        ("silver_cpi", cpi, CPI_SCHEMA),
        ("silver_rates", rates, RATES_SCHEMA),
    ):
        to_spark(spark, frame, schema).writeTo(table(name)).using("iceberg").createOrReplace()
        print(f"SILVER {name}={len(frame)}")
    spark.stop()


if __name__ == "__main__":
    main()
