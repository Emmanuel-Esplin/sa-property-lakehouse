"""Build the dashboard: one static HTML page with the marts' figures inside it.

The page needs no server, no data files and no network, so it opens anywhere, including from disk.
"""

import json
from datetime import date
from pathlib import Path

import duckdb

from ingestion.common.bronze import data_dir

TEMPLATE = Path(__file__).parent / "template.html"
PLACEHOLDER = "__DASHBOARD_DATA__"

# Stats SA's labels are long. These fit a chart axis and keep the meaning.
SHORT_LABELS = {
    "general_dealers": "General dealers",
    "food_beverages_tobacco": "Specialist food and drink",
    "pharma_cosmetics": "Pharmacy and cosmetics",
    "textiles_clothing_footwear": "Clothing and footwear",
    "household_furniture_appliances": "Furniture and appliances",
    "hardware_paint_glass": "Hardware, paint and glass",
    "other_retailers": "All other retailers",
    "total": "All retailers",
}


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    """Query to a list of dicts, with dates as ISO strings.

    Floats keep six decimals. The page rounds for display, and rounding here to two or three
    first would round twice: 1.0750 would show as 1.07.
    """
    cursor = con.execute(sql)
    names = [d[0] for d in cursor.description]
    out = []
    for values in cursor.fetchall():
        row = {}
        for name, value in zip(names, values, strict=True):
            if isinstance(value, date):
                value = value.isoformat()
            elif isinstance(value, float):
                value = round(value, 6)
            row[name] = value
        out.append(row)
    return out


def with_short_labels(records: list[dict]) -> list[dict]:
    return [{**r, "short": SHORT_LABELS.get(r["category"], r["label"])} for r in records]


def collect(warehouse: Path) -> dict:
    """Everything the page shows, read from the gold marts."""
    with duckdb.connect(str(warehouse), read_only=True) as con:
        scorecard = rows(
            con,
            """
            select category, label, segment, latest_month,
                   nominal_growth_pct, real_growth_pct, price_growth_pct, avg_cpi_yoy_pct,
                   above_cpi, shrinking_in_real_terms,
                   months_above_cpi_last_24, months_real_decline_last_24
            from mart_tenant_scorecard
            order by nominal_growth_pct desc
            """,
        )
        growth = rows(
            con,
            """
            select month, category, nominal_yoy_pct, real_yoy_pct, cpi_yoy_pct
            from mart_tenant_growth
            where nominal_yoy_pct is not null
            order by category, month
            """,
        )
        seasonality = rows(
            con,
            """
            select s.category, m.label, s.month_of_year, s.seasonal_index,
                   summary.seasonal_amplitude
            from mart_seasonality_monthly s
            join mart_seasonality_summary summary using (category)
            join (select distinct category, label from mart_tenant_scorecard) m using (category)
            order by summary.seasonal_amplitude desc, s.month_of_year
            """,
        )
        rates = rows(
            con,
            """
            select month, repo_rate_pct, prime_rate_pct, bond_10y_plus_yield_pct,
                   real_bond_yield_pct, repo_change_pts
            from mart_rates_monthly
            order by month
            """,
        )
    if not scorecard:
        raise ValueError(f"{warehouse} has no scorecard rows. Run `make gold` first.")
    return {
        "latest_month": scorecard[0]["latest_month"],
        "scorecard": with_short_labels(scorecard),
        "growth": growth,
        "labels": SHORT_LABELS,
        "seasonality": with_short_labels(seasonality),
        "rates": rates,
    }


def render(data: dict) -> str:
    # "</" inside a <script> would end the element early, so it is escaped.
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    template = TEMPLATE.read_text()
    if template.count(PLACEHOLDER) != 1:
        raise ValueError(f"{TEMPLATE} must contain {PLACEHOLDER} exactly once")
    return template.replace(PLACEHOLDER, payload)


def build(root: Path) -> Path:
    """Write the dashboard next to the warehouse it reads. Returns the page's path."""
    out = root / "dashboard" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(collect(root / "gold" / "warehouse.duckdb")))
    return out


if __name__ == "__main__":
    print(f"Wrote {build(data_dir())}")
