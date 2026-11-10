"""The dashboard is one self-contained page built from the marts."""

import csv
import json
import re
from pathlib import Path

import pytest

from dashboard.build import PLACEHOLDER, SHORT_LABELS, build, collect, render
from tests.test_marts import build_gold

ROOT = Path(__file__).parent.parent
SEED = ROOT / "transform" / "seeds" / "retail_categories.csv"
PUBLISHED = ROOT / "site" / "index.html"


@pytest.fixture
def page(tmp_path, retail, cpi, rates):
    build_gold(tmp_path, retail, cpi, rates)
    return build(tmp_path)


def embedded(html: str) -> dict:
    tag = '<script id="dashboard-data" type="application/json">'
    match = re.search(re.escape(tag) + r"(.*?)</script>", html, re.S)
    return json.loads(match.group(1))


def test_every_seeded_category_has_a_short_label():
    with SEED.open() as f:
        assert {row["category"] for row in csv.DictReader(f)} == set(SHORT_LABELS)


def test_page_is_written_beside_the_warehouse(tmp_path, page):
    assert page == tmp_path / "dashboard" / "index.html"


def test_page_carries_every_mart_it_shows(page):
    data = embedded(page.read_text())
    assert {"scorecard", "growth", "seasonality", "rates", "labels", "latest_month"} <= set(data)
    categories = {r["category"] for r in data["scorecard"]}
    assert categories <= set(SHORT_LABELS)
    assert all(r["short"] == SHORT_LABELS[r["category"]] for r in data["scorecard"])
    assert len(data["seasonality"]) == 12 * len(categories)
    assert data["rates"] and data["growth"]


def test_page_needs_nothing_from_the_network(page):
    html = page.read_text()
    assert PLACEHOLDER not in html
    external = re.search(r"<(script|link)[^>]+(src|href)=", html)
    assert not external, "the page must stay self-contained"


def test_data_cannot_close_its_script_tag(tmp_path, retail, cpi, rates):
    build_gold(tmp_path, retail, cpi, rates)
    data = collect(tmp_path / "gold" / "warehouse.duckdb")
    data["labels"]["total"] = "</script><script>alert(1)</script>"
    html = render(data)
    assert embedded(html)["labels"]["total"] == "</script><script>alert(1)</script>"
    assert html.count("</script>") == 2


def test_published_page_uses_the_current_template():
    """CI can't rebuild site/, so this catches a template change that wasn't republished."""
    html = PUBLISHED.read_text()
    assert render(embedded(html)) == html, "Run `make publish` and commit site/index.html"
