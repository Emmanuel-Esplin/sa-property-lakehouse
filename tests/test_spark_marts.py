"""The Spark marts must give the same answers as the DuckDB marts."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from ingestion.stats_sa.retail_trade import validate_retail, write_silver
from processing.bronze_to_silver.transform import CPI_SCHEMA, RETAIL_SCHEMA, latest_key, to_spark
from processing.silver_to_gold.local import local_session, write_local_marts
from processing.silver_to_gold.marts import build_marts
from scripts.compare_gold import main as compare_gold
from transform.build import build


@pytest.fixture(scope="module")
def spark():
    session = local_session()
    yield session
    session.stop()


def silver_and_duckdb(root: Path, retail, cpi) -> None:
    # The base fixture has tied months, and neither engine promises which one a tie returns.
    retail = retail.copy()
    retail["value_rmillion"] *= 1 + retail["month"].dt.month / 1000
    write_silver(root, retail)
    cpi.to_parquet(root / "silver" / "cpi.parquet", index=False)
    build(root)


def test_spark_marts_match_duckdb(spark, tmp_path, retail, cpi, monkeypatch, capsys):
    monkeypatch.setenv("LAKEHOUSE_DATA_DIR", str(tmp_path))
    silver_and_duckdb(tmp_path, retail, cpi)
    write_local_marts(spark, tmp_path / "silver", tmp_path / "spark_gold")
    assert compare_gold(tmp_path / "spark_gold") == 0, capsys.readouterr().out


def test_comparison_catches_a_wrong_value(spark, tmp_path, retail, cpi, monkeypatch, capsys):
    monkeypatch.setenv("LAKEHOUSE_DATA_DIR", str(tmp_path))
    silver_and_duckdb(tmp_path, retail, cpi)
    write_local_marts(spark, tmp_path / "silver", tmp_path / "spark_gold")
    path = tmp_path / "spark_gold" / "mart_segment_scorecard"
    frame = pd.read_parquet(str(path))
    frame["real_growth_pct"] += 0.01
    for old in path.glob("*.parquet"):
        old.unlink()
    frame.to_parquet(path / "changed.parquet", index=False)
    assert compare_gold(tmp_path / "spark_gold") == 1
    assert "real_growth_pct" in capsys.readouterr().out


def test_spark_gold_checks_stop_on_bad_data(spark, retail, cpi):
    retail["category"] = retail["category"].replace("general_dealers", "new_category")
    to_spark(spark, validate_retail(retail), RETAIL_SCHEMA).createOrReplaceTempView("stg_retail")
    to_spark(spark, cpi, CPI_SCHEMA).createOrReplaceTempView("stg_cpi")
    with pytest.raises(ValueError, match="missing from the seed"):
        build_marts(spark)


def test_to_spark_keeps_every_row_and_type(spark, cpi):
    frame = to_spark(spark, cpi, CPI_SCHEMA)
    assert frame.count() == len(cpi)
    assert frame.schema == CPI_SCHEMA


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
