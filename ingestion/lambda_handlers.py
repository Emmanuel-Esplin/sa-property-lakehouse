"""AWS Lambda entry points. They only move source files into bronze.

Parsing needs pandas and belongs to the PySpark jobs in Phase 3, so this package stays
standard-library only, plus the boto3 that the Lambda runtime provides.
"""

import json
import os
import urllib.parse
from datetime import date

from ingestion.common.s3_writer import put_bronze
from ingestion.sarb.client import API, CPI_SERIES, START_DATE, fetch_series

XLSX_SIGNATURE = b"PK\x03\x04"


def _s3_client():
    import boto3

    return boto3.client("s3")


def cpi_handler(event, context, client=None, fetch=fetch_series) -> dict:
    """Scheduled: store the latest SARB CPI response."""
    client = client or _s3_client()
    raw = fetch(CPI_SERIES, START_DATE, date.today().isoformat())
    if not json.loads(raw):
        raise ValueError("SARB returned no CPI observations")
    stored = put_bronze(
        client, os.environ["LAKE_BUCKET"], "sarb", "cpi", "cpi.json", raw, f"{API}/{CPI_SERIES}"
    )
    return {"key": stored.key, "is_new": stored.is_new}


def retail_handler(event, context, client=None) -> list[dict]:
    """Triggered by an upload to landing: copy each workbook to bronze."""
    client = client or _s3_client()
    results = []
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        # S3 events URL-encode keys, and spaces arrive as "+".
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        content = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        if not content.startswith(XLSX_SIGNATURE):
            raise ValueError(f"{key} is not an .xlsx workbook. Download it again.")
        stored = put_bronze(
            client,
            bucket,
            "stats_sa",
            "retail_trade",
            key.rsplit("/", 1)[-1],
            content,
            f"s3://{bucket}/{key}",
        )
        results.append({"key": stored.key, "is_new": stored.is_new})
    return results
