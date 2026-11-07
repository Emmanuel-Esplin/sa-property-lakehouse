"""SARB interest rates: the policy (repo) rate, prime, and the long government bond yield.

Silver keeps the daily rates as SARB publishes them. Turning days into months happens in dbt, so
that rule lives in one place.
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd

from ingestion.common.bronze import data_dir, write_bronze
from ingestion.sarb.client import API, START_DATE, fetch_series
from ingestion.sarb.series import RATES, SarbSeries

# Wide enough for every South African rate since 2000, narrow enough to catch a unit change.
PLAUSIBLE_PCT = (0, 30)


def parse_rates(series: SarbSeries, raw: bytes) -> pd.DataFrame:
    """Turn one API response into validated daily rows: rate_date, series, value_pct."""
    records = json.loads(raw)
    if not records:
        raise ValueError(f"SARB returned no {series.dataset} observations")

    descriptions = {record["Description"] for record in records}
    if not all(series.described_as in description for description in descriptions):
        raise ValueError(
            f"{series.dataset} no longer described as {series.described_as!r}: {descriptions}"
        )

    frame = pd.DataFrame(
        {
            "rate_date": pd.to_datetime([r["Period"] for r in records]).normalize(),
            "series": series.dataset,
            "value_pct": [r["Value"] for r in records],
        }
    ).sort_values("rate_date", ignore_index=True)

    if frame["rate_date"].duplicated().any():
        raise ValueError(f"{series.dataset} has duplicate dates")
    if frame["value_pct"].isna().any():
        raise ValueError(f"{series.dataset} has null values")
    if not frame["value_pct"].between(*PLAUSIBLE_PCT).all():
        raise ValueError(f"{series.dataset} has values outside {PLAUSIBLE_PCT} %")

    # Rates exist only on business days, so gaps are checked by month, not by day.
    months = frame["rate_date"].dt.to_period("M")
    expected = pd.period_range(months.min(), months.max(), freq="M")
    if months.nunique() != len(expected):
        raise ValueError(f"{series.dataset} has months with no observations")

    frame["rate_date"] = frame["rate_date"].dt.date
    return frame


def run(root: Path) -> pd.DataFrame:
    """Fetch every rate into bronze, then write one validated silver file."""
    end = date.today().isoformat()
    frames = []
    for series in RATES:
        # Parse what was just fetched: if a revision is reverted, its bytes match an older object.
        stored = write_bronze(
            root,
            "sarb",
            series.dataset,
            f"{series.dataset}.json",
            fetch_series(series.code, START_DATE, end),
            origin=f"{API}/{series.code}",
        )
        frames.append(parse_rates(series, stored.path.read_bytes()))

    rates = pd.concat(frames, ignore_index=True)
    silver = root / "silver"
    silver.mkdir(parents=True, exist_ok=True)
    rates.to_parquet(silver / "rates.parquet", index=False)
    return rates


if __name__ == "__main__":
    result = run(data_dir())
    for name, rows in result.groupby("series"):
        print(f"{name}: {len(rows)} days, {rows['rate_date'].min()} to {rows['rate_date'].max()}")
