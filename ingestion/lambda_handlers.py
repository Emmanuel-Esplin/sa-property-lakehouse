"""AWS Lambda entry points. They only move source files into bronze.

Parsing needs pandas, which belongs to the Glue job, so this package stays standard-library only,
plus the boto3 that the Lambda runtime provides.
"""

import json
import os
import urllib.parse
from datetime import date

from ingestion.common.s3_writer import put_bronze
from ingestion.sarb.client import API, START_DATE, fetch_series
from ingestion.sarb.series import ALL as SARB_SERIES

XLSX_SIGNATURE = b"PK\x03\x04"


def _s3_client():
    # Imported here so tests, which pass their own client, don't need boto3 installed.
    import boto3

    return boto3.client("s3")


def sarb_handler(event, context, client=None, fetch=fetch_series) -> list[dict]:
    """Scheduled: store the latest response for every SARB series the project uses."""
    client = client or _s3_client()
    bucket = os.environ["LAKE_BUCKET"]
    end = date.today().isoformat()
    results = []
    for series in SARB_SERIES:
        raw = fetch(series.code, START_DATE, end)
        if not json.loads(raw):
            raise ValueError(f"SARB returned no {series.dataset} observations")
        stored = put_bronze(
            client,
            bucket,
            "sarb",
            series.dataset,
            f"{series.dataset}.json",
            raw,
            f"{API}/{series.code}",
        )
        results.append({"series": series.dataset, "key": stored.key, "is_new": stored.is_new})
    return results


def retail_handler(event, context, client=None) -> list[dict]:
    """Triggered by an upload to landing: copy each workbook to bronze."""
    client = client or _s3_client()
    results = []
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        # S3 events URL-encode keys, and spaces arrive as "+".
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        content = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        # Every .xlsx is a zip file. A saved bot-challenge page is HTML and fails here.
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
