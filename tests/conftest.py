"""Synthetic data with known answers. It only ever exists in pytest's temp folders."""

import openpyxl
import pandas as pd
import pytest

from ingestion.market import reits as market

NOMINAL_GROWTH = {"general_dealers": 0.10, "textiles_clothing_footwear": 0.03}
REAL_GROWTH = {"general_dealers": 0.04, "textiles_clothing_footwear": -0.02}
BASE = {"general_dealers": 1000.0, "textiles_clothing_footwear": 500.0}
CPI_YOY = 5.0
YEARS = range(2022, 2026)


def retail_rows() -> pd.DataFrame:
    """Four years of sales, with December at twice a normal month and fixed annual growth."""
    rows = []
    for year in YEARS:
        for month_number in range(1, 13):
            season = 2.0 if month_number == 12 else 1.0
            month = pd.Timestamp(year, month_number, 1)
            for basis, growth in (("current", NOMINAL_GROWTH), ("constant", REAL_GROWTH)):
                values = {c: BASE[c] * (1 + growth[c]) ** (year - YEARS[0]) * season for c in BASE}
                values["total"] = sum(values.values())
                for category, value in values.items():
                    rows.append((month, category, basis, "unadjusted", value))
    return pd.DataFrame(
        rows, columns=["month", "category", "price_basis", "adjustment", "value_rmillion"]
    )


@pytest.fixture
def retail() -> pd.DataFrame:
    return retail_rows()


@pytest.fixture
def cpi() -> pd.DataFrame:
    months = pd.date_range("2022-01-01", "2025-12-01", freq="MS")
    return pd.DataFrame({"month": months.date, "cpi_yoy_pct": CPI_YOY})


@pytest.fixture
def rates() -> pd.DataFrame:
    """Three days a month. Repo rises 0.25 on 15 June 2024, prime stays 3.5 points above it,
    and the bond yields 9.0, 9.3 and 9.6 in every month, so each monthly average is 9.3."""
    rows = []
    for month in pd.date_range("2022-01-01", "2025-12-01", freq="MS"):
        for day, bond in ((1, 9.0), (15, 9.3), (28, 9.6)):
            rate_date = month.replace(day=day)
            repo = 7.25 if rate_date >= pd.Timestamp(2024, 6, 15) else 7.0
            rows += [
                (rate_date.date(), "repo_rate", repo),
                (rate_date.date(), "prime_rate", repo + 3.5),
                (rate_date.date(), "govt_bond_10y_plus", bond),
            ]
    return pd.DataFrame(rows, columns=["rate_date", "series", "value_pct"])


def reit_price_rows() -> pd.DataFrame:
    """Prices on the 1st, 10th and 20th of each month, 2022 to 2025, flat within a month.

    VKE (retail) rises 1% every month. EQU (logistics) is flat, except for a 5% fall in June 2024,
    the month the rates fixture raises repo by 0.25 points.
    """
    rows = []
    for k, month in enumerate(pd.date_range("2022-01-01", "2025-12-01", freq="MS")):
        for day in (1, 10, 20):
            price_date = month.replace(day=day).date()
            equites = 1900.0 if month >= pd.Timestamp(2024, 6, 1) else 2000.0
            rows += [(price_date, "VKE", 1000 * 1.01**k), (price_date, "EQU", equites)]
    return pd.DataFrame(rows, columns=["price_date", "ticker", "close_cents"])


def reit_distribution_rows() -> pd.DataFrame:
    """VKE pays 30 cents a share every March and September. EQU pays nothing."""
    rows = [
        (pd.Timestamp(year, month, 15).date(), "VKE", 30.0)
        for year in range(2022, 2026)
        for month in (3, 9)
    ]
    return pd.DataFrame(rows, columns=["ex_date", "ticker", "amount_cents"])


@pytest.fixture
def reit_prices() -> pd.DataFrame:
    return reit_price_rows()


@pytest.fixture
def reit_distributions() -> pd.DataFrame:
    return reit_distribution_rows()


def write_market_silver(root, prices=None, distributions=None) -> None:
    """Write REIT silver files. Without data, they are empty, like before any file lands."""
    market.write_silver(
        root, market.PRICES, market.empty_frame(market.PRICES) if prices is None else prices
    )
    market.write_silver(
        root,
        market.DISTRIBUTIONS,
        market.empty_frame(market.DISTRIBUTIONS) if distributions is None else distributions,
    )


# Labels are copied from the real P6242.1 workbook; the values are invented.
RELEASE_CATEGORIES = {
    "General dealers": 1000,
    "Retailers of food, beverages and tobacco in specialised stores": 200,
    "Retailers in pharmaceutical and medical goods,cosmetics and toiletries": 150,
    "Retailers in textiles,clothing,footwear and leather goods": 300,
    "Retailers in household furniture,appliances and equipment": 100,
    "Retailers in hardware,paint and glass": 150,
    "All other retailers": 100,
}


def write_release(
    path,
    label=None,
    unit="R million",
    drop_series=False,
    duplicate=False,
    text_value=False,
    drop_header=None,
    blank=None,
):
    """Write a small workbook in the real layout. Totals start two years before the categories."""
    all_months = [f"MO{m:02d}{y}" for y in range(2022, 2026) for m in range(1, 13)]
    meta = ["H01", "H02", "H03", "H04", "H05", "H15", "H16", "H17", "H25"]
    rows = []
    for price, price_factor in (("At constant prices", 0.8), ("At current prices", 1.0)):
        for adjustment in ("Actual values", "Seasonally adjusted values"):
            total = sum(RELEASE_CATEGORIES.values()) * price_factor
            rows.append(
                ["P6242_1", "Retail", "t", "Total", "", price, adjustment, unit, "Monthly"]
                + [total] * 48
            )
            for name, base in RELEASE_CATEGORIES.items():
                values = [None] * 24 + [base * price_factor] * 24
                row = ["P6242_1", "Retail", "c", "Type of dealer", name, price, adjustment, unit]
                rows.append([*row, "Monthly", *values])
    if label:
        rows[1][4] = label
    if drop_series:
        rows.pop()
    if duplicate:
        rows[-1] = list(rows[-2])
    if text_value:
        rows[0][-1] = ".."
    header = meta + all_months
    if blank:
        for row in rows:
            row[header.index(blank)] = None
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    keep = [i for i, name in enumerate(header) if name != drop_header]
    sheet.append([header[i] for i in keep])
    for row in rows:
        sheet.append([row[i] for i in keep])
    workbook.save(path)
    return path
