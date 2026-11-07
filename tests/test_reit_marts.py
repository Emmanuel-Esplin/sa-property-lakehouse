"""The REIT marts, built by dbt from synthetic prices with answers worked out here by hand."""

import duckdb
import pandas as pd
import pytest

from tests.test_marts import build_gold

# Prices run from January 2022. December 2025 is the latest month, so it is left out as unfinished.
VKE_GROWTH = 1.01
VKE_START = 1000.0
DISTRIBUTION = 30.0


def vke_close(months_since_jan_2022: int) -> float:
    return VKE_START * VKE_GROWTH**months_since_jan_2022


@pytest.fixture
def warehouse(tmp_path, retail, cpi, rates, reit_prices, reit_distributions):
    return build_gold(tmp_path, retail, cpi, rates, reit_prices, reit_distributions)


def one(warehouse, sql):
    with duckdb.connect(str(warehouse), read_only=True) as connection:
        return connection.sql(sql).fetchdf().iloc[0]


def test_total_return_adds_the_distribution_in_its_ex_month(warehouse):
    row = one(
        warehouse, "select * from mart_reit_monthly where ticker = 'VKE' and month = '2024-03-01'"
    )
    march_2024 = 26  # months after January 2022
    assert row["price_return_pct"] == pytest.approx(1.0)
    expected = (vke_close(march_2024) + DISTRIBUTION) / vke_close(march_2024 - 1) - 1
    assert row["total_return_pct"] == pytest.approx(100 * expected)


def test_distribution_yield_uses_the_last_twelve_months(warehouse):
    row = one(
        warehouse, "select * from mart_reit_monthly where ticker = 'VKE' and month = '2025-11-01'"
    )
    november_2025 = 46
    assert row["distribution_yield_pct"] == pytest.approx(
        100 * 2 * DISTRIBUTION / vke_close(november_2025)
    )
    assert row["yield_spread_to_bond_pts"] == pytest.approx(row["distribution_yield_pct"] - 9.3)


def test_distribution_yield_counts_exactly_twelve_months(warehouse):
    # The window ending August 2025 starts in September 2024, so it holds two payments.
    # One month shorter, it would start in October and hold only March's.
    row = one(
        warehouse, "select * from mart_reit_monthly where ticker = 'VKE' and month = '2025-08-01'"
    )
    august_2025 = 43
    assert row["distribution_yield_pct"] == pytest.approx(
        100 * 2 * DISTRIBUTION / vke_close(august_2025)
    )


def test_distribution_yield_waits_for_a_full_year(warehouse):
    row = one(
        warehouse, "select * from mart_reit_monthly where ticker = 'VKE' and month = '2022-11-01'"
    )
    assert pd.isna(row["distribution_yield_pct"])


def test_three_year_return_compounds_every_month_and_removes_inflation(warehouse):
    row = one(warehouse, "select * from mart_reit_returns where ticker = 'VKE'")
    assert str(row["as_at_month"])[:10] == "2025-11-01"

    # The 36 months ending November 2025 are months 11 to 46 after January 2022.
    growth = 1.0
    for k in range(11, 47):
        paid = DISTRIBUTION if k % 12 in (2, 8) else 0.0  # March and September
        growth *= (vke_close(k) + paid) / vke_close(k - 1)
    assert row["annual_return_3y_pct"] == pytest.approx(100 * (growth ** (1 / 3) - 1))
    assert row["real_annual_return_3y_pct"] == pytest.approx(
        100 * ((growth / 1.05**3) ** (1 / 3) - 1)
    )


def test_five_year_return_needs_five_years_of_prices(warehouse):
    row = one(warehouse, "select * from mart_reit_returns where ticker = 'VKE'")
    assert pd.isna(row["annual_return_5y_pct"])


def test_sector_sensitivity_recovers_the_built_in_rate_response(warehouse):
    # EQU falls 5% only in June 2024, when repo rises 0.25 points: -5 / 0.25 = -20 per point.
    row = one(warehouse, "select * from mart_sector_rate_sensitivity where sector = 'logistics'")
    assert row["hike_months"] == 1 and row["cut_months"] == 0
    assert row["avg_return_hike_months_pct"] == pytest.approx(-5.0)
    assert row["avg_return_hold_months_pct"] == pytest.approx(0.0)
    assert row["return_per_rate_point_pct"] == pytest.approx(-20.0)


def test_reit_marts_are_empty_without_reit_files(tmp_path, retail, cpi, rates):
    warehouse = build_gold(tmp_path, retail, cpi, rates)
    for mart in ("mart_reit_monthly", "mart_reit_returns", "mart_sector_rate_sensitivity"):
        assert one(warehouse, f"select count(*) as n from {mart}")["n"] == 0
