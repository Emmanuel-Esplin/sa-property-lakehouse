"""The dbt marts, built locally on DuckDB from synthetic data with known answers."""

import duckdb
import pandas as pd
import pytest

from ingestion.stats_sa.retail_trade import write_silver
from transform.run import DbtFailed, build


def build_gold(root, retail, cpi, rates):
    write_silver(root, retail)
    cpi.to_parquet(root / "silver" / "cpi.parquet", index=False)
    rates.to_parquet(root / "silver" / "rates.parquet", index=False)
    return build(root)


@pytest.fixture
def warehouse(tmp_path, retail, cpi, rates):
    return build_gold(tmp_path, retail, cpi, rates)


def query(warehouse, sql):
    with duckdb.connect(str(warehouse), read_only=True) as connection:
        return connection.sql(sql).fetchdf()


def test_growth_splits_into_real_and_price(warehouse):
    row = query(
        warehouse,
        """select * from mart_tenant_growth
           where category = 'general_dealers' and month = '2025-06-01'""",
    ).iloc[0]
    assert row["nominal_yoy_pct"] == pytest.approx(10)
    assert row["real_yoy_pct"] == pytest.approx(4)
    assert row["price_yoy_pct"] == pytest.approx((1.10 / 1.04 - 1) * 100)
    assert row["nominal_minus_cpi_pts"] == pytest.approx(5)


def test_first_year_has_no_growth(warehouse):
    nulls = query(
        warehouse,
        "select count(*) as n from mart_tenant_growth where year(month) = 2022 "
        "and nominal_yoy_pct is null",
    )
    assert nulls["n"].iloc[0] == 12 * 3


def test_scorecard_classifies_categories(warehouse):
    card = query(warehouse, "select * from mart_tenant_scorecard").set_index("category")
    grocer = card.loc["general_dealers"]
    clothing = card.loc["textiles_clothing_footwear"]

    assert grocer["nominal_growth_pct"] == pytest.approx(10)
    assert bool(grocer["above_cpi"]) and not bool(grocer["shrinking_in_real_terms"])
    assert grocer["months_above_cpi_last_24"] == 24

    assert clothing["real_growth_pct"] == pytest.approx(-2)
    assert not bool(clothing["above_cpi"]) and bool(clothing["shrinking_in_real_terms"])
    assert clothing["months_real_decline_last_24"] == 24


def test_seasonality_finds_december_peak(warehouse):
    row = query(
        warehouse, "select * from mart_seasonality_summary where category = 'general_dealers'"
    ).iloc[0]
    assert row["peak_month"] == 12
    assert row["peak_index"] == pytest.approx(24 / 13)
    assert row["trough_index"] == pytest.approx(12 / 13)
    assert row["years_used"] == 4


def test_seasonality_skips_lockdown_years(tmp_path, retail, cpi, rates):
    shifted = retail.copy()
    shifted["month"] = shifted["month"] - pd.DateOffset(years=2)
    extra_cpi = pd.DataFrame(
        {"month": pd.date_range("2020-01-01", "2023-12-01", freq="MS").date, "cpi_yoy_pct": 5.0}
    )
    warehouse = build_gold(tmp_path, shifted, extra_cpi, rates)
    used = query(warehouse, "select distinct years_used from mart_seasonality_summary")
    assert used["years_used"].tolist() == [2]  # 2022 and 2023 only


def test_build_rejects_category_missing_from_seed(tmp_path, retail, cpi, rates):
    retail["category"] = retail["category"].replace("general_dealers", "new_category")
    with pytest.raises(DbtFailed, match="relationships"):
        build_gold(tmp_path, retail, cpi, rates)


def test_build_rejects_months_without_cpi(tmp_path, retail, cpi, rates):
    with pytest.raises(DbtFailed, match="assert_retail_months_have_cpi"):
        build_gold(tmp_path, retail, cpi[cpi["month"] < pd.Timestamp(2025, 1, 1).date()], rates)


def write_unchecked_silver(root, retail, cpi, rates):
    """Skip the Python contract, to prove dbt's own tests catch the same problems."""
    silver = root / "silver"
    silver.mkdir(parents=True)
    retail.assign(month=retail["month"].dt.date).to_parquet(silver / "retail_trade.parquet")
    cpi.to_parquet(silver / "cpi.parquet", index=False)
    rates.to_parquet(silver / "rates.parquet", index=False)


def test_dbt_catches_a_month_gap(tmp_path, retail, cpi, rates):
    gap = retail[~((retail["month"] == "2023-06-01") & (retail["category"] == "total"))]
    write_unchecked_silver(tmp_path, gap, cpi, rates)
    with pytest.raises(DbtFailed, match="no_month_gaps"):
        build(tmp_path)


def test_dbt_catches_duplicate_rows(tmp_path, retail, cpi, rates):
    write_unchecked_silver(tmp_path, pd.concat([retail, retail.head(1)]), cpi, rates)
    with pytest.raises(DbtFailed, match="unique_combination"):
        build(tmp_path)


def test_build_needs_silver_inputs(tmp_path):
    with pytest.raises(FileNotFoundError, match="make cpi"):
        build(tmp_path)


def test_warehouse_can_be_queried_after_the_build(warehouse):
    assert query(warehouse, "select count(*) as n from stg_retail")["n"].iloc[0] > 0
    assert query(warehouse, "select count(*) as n from stg_cpi")["n"].iloc[0] > 0


def test_segment_scorecard_excludes_total_and_adds_up_segments(warehouse):
    card = query(warehouse, "select * from mart_segment_scorecard").set_index("segment")
    assert set(card.index) == {"defensive", "discretionary"}
    assert card.loc["defensive", "real_growth_pct"] == pytest.approx(4)
    assert card.loc["discretionary", "nominal_growth_pct"] == pytest.approx(3)


def test_rates_use_month_end_policy_rates_and_average_bond_yield(warehouse):
    row = query(warehouse, "select * from mart_rates_monthly where month = '2024-06-01'").iloc[0]
    assert row["repo_rate_pct"] == pytest.approx(7.25)
    assert row["prime_rate_pct"] == pytest.approx(10.75)
    assert row["repo_change_pts"] == pytest.approx(0.25)
    assert row["bond_10y_plus_yield_pct"] == pytest.approx(9.3)
    assert row["real_bond_yield_pct"] == pytest.approx(9.3 - 5.0)


def test_rates_leave_out_the_unfinished_latest_month(warehouse):
    months = query(
        warehouse, "select min(month) as first, max(month) as last from mart_rates_monthly"
    )
    assert str(months["first"].iloc[0])[:10] == "2022-01-01"
    assert str(months["last"].iloc[0])[:10] == "2025-11-01"


def test_rates_start_when_every_series_has_started(tmp_path, retail, cpi, rates):
    # In the real data, repo starts on 31 December 2001 and the others on 2 January 2002.
    early_repo = pd.DataFrame(
        [(pd.Timestamp(2021, 12, 31).date(), "repo_rate", 7.0)], columns=rates.columns
    )
    warehouse = build_gold(tmp_path, retail, cpi, pd.concat([early_repo, rates]))
    first = query(warehouse, "select min(month) as first from mart_rates_monthly")["first"]
    assert str(first.iloc[0])[:10] == "2022-01-01"


def test_dbt_catches_prime_breaking_from_repo(tmp_path, retail, cpi, rates):
    broken = rates.copy()
    broken.loc[broken["series"] == "prime_rate", "value_pct"] += 0.5
    with pytest.raises(DbtFailed, match="assert_prime_is_repo_plus_350"):
        build_gold(tmp_path, retail, cpi, broken)
