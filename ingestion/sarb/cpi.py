"""Headline CPI (year-on-year %) from the South African Reserve Bank's public web API."""

import json
from datetime import date
from pathlib import Path

import pandas as pd

from ingestion.common.bronze import data_dir, write_bronze
from ingestion.sarb.client import API, START_DATE, fetch_series
from ingestion.sarb.series import CPI


def parse_cpi(raw: bytes) -> pd.DataFrame:
    """Turn the API response into one validated row per month."""
    records = json.loads(raw)
    if not records:
        raise ValueError("SARB returned no CPI observations")

    descriptions = {record["Description"] for record in records}
    if not all(CPI.described_as in description for description in descriptions):
        raise ValueError(f"CPI series no longer described as {CPI.described_as!r}: {descriptions}")

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
    """Fetch CPI into bronze, then write the validated silver file."""
    end = date.today().isoformat()
    # Parse what was just fetched: if a revision is reverted, its bytes match an older object.
    stored = write_bronze(
        root,
        "sarb",
        CPI.dataset,
        f"{CPI.dataset}.json",
        fetch_series(CPI.code, START_DATE, end),
        origin=f"{API}/{CPI.code}",
    )
    frame = parse_cpi(stored.path.read_bytes())
    silver = root / "silver"
    silver.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(silver / "cpi.parquet", index=False)
    return frame


if __name__ == "__main__":
    cpi = run(data_dir())
    print(f"CPI: {len(cpi)} months, {cpi['month'].iloc[0]} to {cpi['month'].iloc[-1]}")
