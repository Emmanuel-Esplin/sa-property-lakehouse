"""The SARB CPI parser: what it accepts, and each rule it enforces."""

import json

import pandas as pd
import pytest

from ingestion.sarb.cpi import parse_cpi

DESCRIPTION = "CONSUMER PRICES Total (All urban areas) 12-Term % change"


def payload(*periods, value=4.5, description=DESCRIPTION):
    return json.dumps(
        [{"Period": p, "Description": description, "Value": value} for p in periods]
    ).encode()


def test_parses_month_end_periods_to_month_start():
    frame = parse_cpi(payload("2026-09-30T00:00:00", "2026-08-31T00:00:00"))
    assert frame["month"].tolist() == [
        pd.Timestamp(2026, 8, 1).date(),
        pd.Timestamp(2026, 9, 1).date(),
    ]
    assert frame["cpi_yoy_pct"].tolist() == [4.5, 4.5]


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"[]", "no CPI"),
        (payload("2026-09-30", description="CPI index"), "no longer described"),
        (payload("2026-09-30", "2026-07-31"), "month gaps"),
        (payload("2026-09-30", "2026-09-30"), "duplicate"),
        (payload("2026-09-30", value=450), "plausible"),
    ],
)
def test_rejects_bad_responses(raw, message):
    with pytest.raises(ValueError, match=message):
        parse_cpi(raw)
