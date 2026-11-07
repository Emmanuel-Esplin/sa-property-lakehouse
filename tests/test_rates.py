"""The SARB rates parser: what it accepts, and each rule it enforces."""

import json

import pytest

from ingestion.sarb.rates import parse_rates
from ingestion.sarb.series import RATES

REPO = next(series for series in RATES if series.dataset == "repo_rate")
DESCRIPTION = "The SARB Policy Rate (SPR) is the interest rate set by the Monetary Policy Committee"


def payload(*periods, value=7.25, description=DESCRIPTION):
    return json.dumps(
        [{"Period": p, "Description": description, "Value": value} for p in periods]
    ).encode()


def test_parses_one_row_per_business_day():
    frame = parse_rates(REPO, payload("2026-11-06T00:00:00", "2026-11-05T00:00:00"))
    assert [str(d) for d in frame["rate_date"]] == ["2026-11-05", "2026-11-06"]
    assert set(frame["series"]) == {"repo_rate"}
    assert frame["value_pct"].tolist() == [7.25, 7.25]


def test_allows_weekends_and_holidays_without_rows():
    frame = parse_rates(REPO, payload("2026-10-30", "2026-11-02"))
    assert len(frame) == 2


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"[]", "no repo_rate"),
        (payload("2026-11-05", description="Prime lending rate"), "no longer described"),
        (payload("2026-11-05", "2026-11-05"), "duplicate dates"),
        (payload("2026-11-05", value=725), "outside"),
        (payload("2026-09-30", "2026-11-02"), "months with no observations"),
    ],
)
def test_rejects_bad_responses(raw, message):
    with pytest.raises(ValueError, match=message):
        parse_rates(REPO, raw)


def test_rejects_a_null_value():
    raw = json.dumps([{"Period": "2026-11-05", "Description": DESCRIPTION, "Value": None}])
    with pytest.raises(ValueError, match="null"):
        parse_rates(REPO, raw.encode())


def test_every_series_has_a_unique_dataset_name():
    names = [series.dataset for series in RATES]
    assert len(names) == len(set(names))
