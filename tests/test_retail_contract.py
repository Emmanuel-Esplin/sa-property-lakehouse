import pandas as pd
import pytest

from ingestion.stats_sa.retail_trade import (
    ReleaseFormatNotMapped,
    land_release,
    landing_dir,
    parse_release,
    run,
    validate_retail,
)
from tests.conftest import write_release


def test_valid_data_passes(retail):
    assert len(validate_retail(retail)) == len(retail)


def test_rejects_month_gap(retail):
    gap = retail[~((retail["month"] == "2023-06-01") & (retail["category"] == "total"))]
    with pytest.raises(ValueError, match="Month gap"):
        validate_retail(gap)


def test_rejects_duplicates(retail):
    with pytest.raises(ValueError, match="duplicate"):
        validate_retail(pd.concat([retail, retail.head(1)]))


def test_rejects_non_positive_sales(retail):
    retail.loc[0, "value_rmillion"] = 0
    with pytest.raises(ValueError, match="positive"):
        validate_retail(retail)


def test_rejects_missing_price_basis(retail):
    with pytest.raises(ValueError, match="current and constant"):
        validate_retail(retail[retail["price_basis"] == "current"])


def test_rejects_one_category_missing_constant_prices(retail):
    one_sided = retail[
        ~((retail["category"] == "general_dealers") & (retail["price_basis"] == "constant"))
    ]
    with pytest.raises(ValueError, match="both current and constant"):
        validate_retail(one_sided)


def test_rejects_total_that_does_not_reconcile(retail):
    retail.loc[retail["category"] == "total", "value_rmillion"] *= 1.5
    with pytest.raises(ValueError, match="differ from total"):
        validate_retail(retail)


def test_rejects_saved_bot_challenge_page(tmp_path):
    folder = landing_dir(tmp_path)
    folder.mkdir(parents=True)
    (folder / "retail.xlsx").write_bytes(b'<html><script src="/_Incapsula"></script></html>')
    with pytest.raises(ValueError, match="HTML page"):
        land_release(tmp_path)


def test_landing_is_idempotent(tmp_path):
    folder = landing_dir(tmp_path)
    folder.mkdir(parents=True)
    (folder / "retail.xlsx").write_bytes(b"PK\x03\x04 data")
    first = land_release(tmp_path)
    second = land_release(tmp_path)
    manifest = tmp_path / "bronze/stats_sa/retail_trade/manifest.jsonl"
    assert len(manifest.read_text().splitlines()) == 1
    assert first.is_new and not second.is_new and first.path == second.path


def test_landing_ignores_other_formats_and_finds_nested_workbook(tmp_path):
    nested = landing_dir(tmp_path) / "EXCEL"
    nested.mkdir(parents=True)
    (nested / "retail.xlsx").write_bytes(b"PK\x03\x04 data")
    (landing_dir(tmp_path) / "release.pdf").write_bytes(b"%PDF")
    (nested / "legacy.xls").write_bytes(b"old")
    assert land_release(tmp_path).path.name.endswith("retail.xlsx")


def test_landing_refuses_two_workbooks(tmp_path):
    folder = landing_dir(tmp_path)
    folder.mkdir(parents=True)
    (folder / "a.xlsx").write_bytes(b"a")
    (folder / "b.xlsx").write_bytes(b"b")
    with pytest.raises(ValueError, match="Expected one workbook"):
        land_release(tmp_path)


def test_run_without_files_returns_none(tmp_path, capsys):
    assert run(tmp_path) is None
    assert "statssa.gov.za" in capsys.readouterr().err


def test_run_writes_silver_from_a_workbook(tmp_path):
    folder = landing_dir(tmp_path)
    folder.mkdir(parents=True)
    write_release(folder / "retail.xlsx")
    silver = pd.read_parquet(run(tmp_path))
    assert len(silver) == 32 * 24


def test_parser_maps_labels_to_the_contract(tmp_path):
    frame = parse_release(write_release(tmp_path / "r.xlsx"))
    assert frame["category"].nunique() == 8
    assert set(frame["price_basis"]) == {"current", "constant"}
    assert set(frame["adjustment"]) == {"unadjusted", "seasonally_adjusted"}
    row = frame[
        (frame["month"] == "2024-01-01")
        & (frame["category"] == "general_dealers")
        & (frame["price_basis"] == "constant")
        & (frame["adjustment"] == "unadjusted")
    ]
    assert row["value_rmillion"].tolist() == [800.0]


def test_parser_trims_to_months_every_series_has(tmp_path):
    frame = parse_release(write_release(tmp_path / "r.xlsx"))
    assert frame["month"].min() == pd.Timestamp(2024, 1, 1)
    assert frame["month"].max() == pd.Timestamp(2025, 12, 1)


def test_parser_keeps_a_gap_so_validation_catches_it(tmp_path):
    frame = parse_release(write_release(tmp_path / "r.xlsx", blank="MO062024"))
    with pytest.raises(ValueError, match="Month gap"):
        validate_retail(frame)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"label": "Brand new category"}, "unknown series labels"),
        ({"unit": "R thousand"}, "unexpected source, unit"),
        ({"drop_series": True}, "expected 32"),
        ({"duplicate": True}, "repeats series"),
        ({"text_value": True}, "non-numeric"),
        ({"drop_header": "H16"}, "missing columns"),
    ],
)
def test_parser_rejects_layout_changes(tmp_path, change, message):
    path = write_release(tmp_path / "r.xlsx", **change)
    with pytest.raises(ReleaseFormatNotMapped, match=message):
        parse_release(path)


def test_parser_rejects_a_file_that_is_not_a_workbook(tmp_path):
    path = tmp_path / "r.xlsx"
    path.write_bytes(b"PK\x03\x04 data")
    with pytest.raises(ReleaseFormatNotMapped, match="could not be read"):
        parse_release(path)
