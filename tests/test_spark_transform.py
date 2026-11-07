"""Spark bronze-to-silver helpers."""

from datetime import UTC, datetime

import pytest

from processing.bronze_to_silver.transform import CPI_SCHEMA, RATES_SCHEMA, latest_key, to_spark
from processing.local import local_session


@pytest.fixture(scope="module")
def spark():
    session = local_session()
    yield session
    session.stop()


def test_to_spark_keeps_every_row_and_type(spark, cpi):
    frame = to_spark(spark, cpi, CPI_SCHEMA)
    assert frame.count() == len(cpi)
    assert frame.schema == CPI_SCHEMA


def test_rates_fit_their_spark_schema(spark, rates):
    frame = to_spark(spark, rates, RATES_SCHEMA)
    assert frame.count() == len(rates)
    assert frame.schema == RATES_SCHEMA


def test_latest_key_picks_the_newest_vintage():
    class Pages:
        def paginate(self, **_):
            return [
                {
                    "Contents": [
                        {"Key": "old", "LastModified": datetime(2026, 1, 1, tzinfo=UTC)},
                        {"Key": "new", "LastModified": datetime(2026, 2, 1, tzinfo=UTC)},
                    ]
                },
                {"Contents": [{"Key": "mid", "LastModified": datetime(2026, 1, 15, tzinfo=UTC)}]},
            ]

    class Client:
        def get_paginator(self, _):
            return Pages()

    assert latest_key(Client(), "lake", "bronze/") == "new"


def test_latest_key_refuses_an_empty_prefix():
    class Client:
        def get_paginator(self, _):
            class Pages:
                def paginate(self, **_):
                    return [{}]

            return Pages()

    with pytest.raises(FileNotFoundError):
        latest_key(Client(), "lake", "bronze/")
