"""The REIT landing files: what is accepted, and each rule that refuses a file."""

import pandas as pd
import pytest

from ingestion.market.reits import DISTRIBUTIONS, PRICES, landing_dir, read_landed, run

PRICE_HEADER = "date,ticker,close_cents\n"
DISTRIBUTION_HEADER = "ticker,ex_date,amount_cents\n"


def land(root, kind, name, text):
    folder = landing_dir(root, kind)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text)


def prices_csv(*rows):
    return PRICE_HEADER + "".join(f"{row}\n" for row in rows)


STEADY = ("2026-01-05,VKE,1500", "2026-01-12,VKE,1510", "2026-01-19,VKE,1505")


def test_valid_files_reach_silver(tmp_path):
    land(tmp_path, PRICES, "vke.csv", prices_csv(*STEADY))
    land(tmp_path, DISTRIBUTIONS, "vke.csv", DISTRIBUTION_HEADER + "VKE,2026-01-12,61.5\n")
    prices, distributions = run(tmp_path)
    assert len(prices) == 3 and len(distributions) == 1
    silver = pd.read_parquet(tmp_path / "silver" / "reit_prices.parquet")
    assert list(silver.columns) == ["price_date", "ticker", "close_cents"]


def test_no_files_write_empty_silver(tmp_path):
    prices, distributions = run(tmp_path)
    assert prices.empty and distributions.empty
    assert pd.read_parquet(tmp_path / "silver" / "reit_distributions.parquet").empty


def test_tickers_are_trimmed_and_upper_cased(tmp_path):
    land(tmp_path, PRICES, "vke.csv", prices_csv("2026-01-05, vke ,1500"))
    prices, _ = run(tmp_path)
    assert prices["ticker"].tolist() == ["VKE"]


def test_identical_repeats_across_files_are_dropped(tmp_path):
    land(tmp_path, PRICES, "first.csv", prices_csv(*STEADY))
    land(tmp_path, PRICES, "overlap.csv", prices_csv(*STEADY[1:]))
    prices, _ = run(tmp_path)
    assert len(prices) == 3


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("<html><script></script></html>", "HTML page"),
        ("day,ticker,close\n2026-01-05,VKE,1500\n", "columns must be"),
        (prices_csv("05/01/2026,VKE,1500"), "date '05/01/2026' is not valid"),
        (prices_csv("2026-01-05,VKE,n/a"), "close_cents 'n/a' is not valid"),
        (prices_csv("2026-01-05,VKE,"), "close_cents '' is not valid"),
        (prices_csv("2026-01-05,ZZZ,1500"), "Unknown tickers \\['ZZZ'\\]"),
        (prices_csv("2026-01-05,VKE,0"), "positive"),
        (prices_csv("2026-01-05,VKE,1500", "2026-02-05,VKE,1500"), "no prices in the 31 days"),
        (prices_csv("2026-01-05,VKE,1500", "2026-01-06,VKE,15"), "rand mixed with prices in cents"),
    ],
)
def test_price_files_are_refused(tmp_path, text, message):
    land(tmp_path, PRICES, "bad.csv", text)
    with pytest.raises(ValueError, match=message):
        run(tmp_path)


def test_conflicting_repeats_name_both_files(tmp_path):
    land(tmp_path, PRICES, "a.csv", prices_csv("2026-01-05,VKE,1500"))
    land(tmp_path, PRICES, "b.csv", prices_csv("2026-01-05,VKE,1600"))
    with pytest.raises(
        ValueError, match=r"Conflicting close_cents for VKE on 2026-01-05 .*a\.csv.*b\.csv"
    ):
        run(tmp_path)


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ("VKE,2025-12-01,61.5", "outside its prices"),
        ("EQU,2026-01-12,40", "EQU, which has no prices"),
        ("VKE,2026-01-12,-1", "positive"),
    ],
)
def test_distribution_files_are_refused(tmp_path, row, message):
    land(tmp_path, PRICES, "vke.csv", prices_csv(*STEADY))
    land(tmp_path, DISTRIBUTIONS, "bad.csv", DISTRIBUTION_HEADER + row + "\n")
    with pytest.raises(ValueError, match=message):
        run(tmp_path)


def test_a_refused_file_leaves_silver_unchanged(tmp_path):
    land(tmp_path, PRICES, "vke.csv", prices_csv(*STEADY))
    run(tmp_path)
    land(tmp_path, DISTRIBUTIONS, "bad.csv", DISTRIBUTION_HEADER + "VKE,2025-12-01,61.5\n")
    with pytest.raises(ValueError):
        run(tmp_path)
    assert pd.read_parquet(tmp_path / "silver" / "reit_distributions.parquet").empty


def test_every_landed_file_is_kept_in_bronze(tmp_path):
    land(tmp_path, PRICES, "vke.csv", prices_csv(*STEADY))
    read_landed(tmp_path, PRICES)
    manifest = tmp_path / "bronze" / "market" / "prices" / "manifest.jsonl"
    assert len(manifest.read_text().splitlines()) == 1
