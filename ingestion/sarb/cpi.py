"""Headline CPI (year-on-year %) from the South African Reserve Bank's public web API."""

import json
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

from ingestion.common.bronze import data_dir, write_bronze

API = "https://custom.resbank.co.za/SarbWebApi/WebIndicators/Shared/GetTimeseriesObservations"
CPI_SERIES = "CPI1000F"
START_DATE = "2000-01-01"
USER_AGENT = "sa-property-lakehouse/0.1"
# SARB describes the series this way. If the wording changes, the measure may have changed too.
EXPECTED_MEASURE = "12-Term % change"


def fetch_series(code: str, start: str, end: str, attempts: int = 3) -> bytes:
    url = f"{API}/{code}/{start}/{end}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                content_type = response.headers.get("Content-Type", "")
                body = response.read()
            if "json" not in content_type:
                raise ValueError(f"Expected JSON from {url}, got {content_type!r}")
            return body
        except urllib.error.URLError:
            if attempt == attempts:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def parse_cpi(raw: bytes) -> pd.DataFrame:
    """Turn the API response into one validated row per month."""
    records = json.loads(raw)
    if not records:
        raise ValueError("SARB returned no CPI observations")

    descriptions = {record["Description"] for record in records}
    if not all(EXPECTED_MEASURE in description for description in descriptions):
        raise ValueError(f"CPI series no longer described as {EXPECTED_MEASURE!r}: {descriptions}")

    frame = pd.DataFrame(
        {
            "month": pd.to_datetime([r["Period"] for r in records]).to_period("M").to_timestamp(),
            "cpi_yoy_pct": [r["Value"] for r in records],
        }
    ).sort_values("month", ignore_index=True)

    if frame["month"].duplicated().any():
        raise ValueError("CPI has duplicate months")
    if frame["cpi_yoy_pct"].isna().any():
        raise ValueError("CPI has null values")
    expected = pd.date_range(frame["month"].min(), frame["month"].max(), freq="MS")
    if len(expected) != len(frame):
        raise ValueError(f"CPI has month gaps: {sorted(set(expected) - set(frame['month']))}")
    if not frame["cpi_yoy_pct"].between(-5, 30).all():
        raise ValueError("CPI has values outside the plausible range of -5% to 30%")
    frame["month"] = frame["month"].dt.date
    return frame


def run(root: Path) -> pd.DataFrame:
    end = date.today().isoformat()
    # Parse what was just fetched: if a revision is reverted, its bytes match an older object.
    stored = write_bronze(
        root,
        "sarb",
        "cpi",
        "cpi.json",
        fetch_series(CPI_SERIES, START_DATE, end),
        origin=f"{API}/{CPI_SERIES}",
    )
    frame = parse_cpi(stored.path.read_bytes())
    silver = root / "silver"
    silver.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(silver / "cpi.parquet", index=False)
    return frame


if __name__ == "__main__":
    cpi = run(data_dir())
    print(f"CPI: {len(cpi)} months, {cpi['month'].iloc[0]} to {cpi['month'].iloc[-1]}")
