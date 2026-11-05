"""Retail trade sales (Stats SA P6242.1): landing zone, parser, silver contract and validation.

Stats SA's site challenges scripted clients with bot protection, so the time series workbook is
downloaded by hand in a browser and dropped into the landing folder. See the README for the steps.
"""

import re
import sys
import zipfile
from pathlib import Path

import openpyxl
import pandas as pd

from ingestion.common.bronze import BronzeObject, data_dir, write_bronze

PRICE_BASES = {"current", "constant"}
ADJUSTMENTS = {"unadjusted", "seasonally_adjusted"}
COLUMNS = ["month", "category", "price_basis", "adjustment", "value_rmillion"]
SERIES_KEY = ["category", "price_basis", "adjustment"]
# Published categories are rounded, so the total will not match their sum exactly.
TOTAL_TOLERANCE = 0.01

CATEGORY_BY_LABEL = {
    "General dealers": "general_dealers",
    "Retailers of food, beverages and tobacco in specialised stores": "food_beverages_tobacco",
    "Retailers in pharmaceutical and medical goods,cosmetics and toiletries": "pharma_cosmetics",
    "Retailers in textiles,clothing,footwear and leather goods": "textiles_clothing_footwear",
    "Retailers in household furniture,appliances and equipment": ("household_furniture_appliances"),
    "Retailers in hardware,paint and glass": "hardware_paint_glass",
    "All other retailers": "other_retailers",
}
PRICE_BY_LABEL = {"At current prices": "current", "At constant prices": "constant"}
ADJUSTMENT_BY_LABEL = {
    "Actual values": "unadjusted",
    "Seasonally adjusted values": "seasonally_adjusted",
}
EXPECTED_SERIES = (len(CATEGORY_BY_LABEL) + 1) * len(PRICE_BASES) * len(ADJUSTMENTS)
MONTH_COLUMN = re.compile(r"^MO(\d{2})(\d{4})$")
REQUIRED_HEADERS = {"H01", "H04", "H05", "H15", "H16", "H17", "H25"}


class ReleaseFormatNotMapped(RuntimeError):
    """The workbook does not match the layout this parser was written against."""


def landing_dir(root: Path) -> Path:
    return root / "landing" / "stats_sa" / "retail_trade"


def land_release(root: Path) -> BronzeObject | None:
    """Copy the landed workbook to bronze. Other formats and old archives are left alone.

    Exactly one workbook is allowed, because the file itself does not say which release it is.
    """
    folder = landing_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    workbooks = sorted(p for p in folder.rglob("*.xlsx") if not p.name.startswith((".", "~$")))
    if not workbooks:
        return None
    if len(workbooks) > 1:
        names = ", ".join(p.name for p in workbooks)
        raise ValueError(f"Expected one workbook in {folder}, found {len(workbooks)}: {names}")

    path = workbooks[0]
    content = path.read_bytes()
    if b"<html" in content[:1024].lower():
        raise ValueError(f"{path.name} is an HTML page, not a data file. Download it again.")
    return write_bronze(
        root, "stats_sa", "retail_trade", path.name, content, origin=f"manual:{path}"
    )


def parse_release(path: Path) -> pd.DataFrame:
    """Convert a P6242.1 workbook to the silver contract, keeping only months all series share."""
    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except (zipfile.BadZipFile, OSError, KeyError) as error:
        raise ReleaseFormatNotMapped(f"{path.name} could not be read as a workbook") from error
    rows = list(workbook.worksheets[0].iter_rows(values_only=True))
    workbook.close()
    if not rows:
        raise ReleaseFormatNotMapped(f"{path.name} is empty")

    header = rows[0]
    if missing := REQUIRED_HEADERS - set(header):
        raise ReleaseFormatNotMapped(f"{path.name} is missing columns: {sorted(missing)}")
    position = {name: index for index, name in enumerate(header)}
    months = {
        index: pd.Timestamp(int(match[2]), int(match[1]), 1)
        for index, name in enumerate(header)
        if (match := MONTH_COLUMN.match(str(name)))
    }
    if not months:
        raise ReleaseFormatNotMapped(f"{path.name} has no MOmmyyyy columns")

    records, seen = [], set()
    for row in rows[1:]:
        key = _series_key(row, position, path.name)
        if key in seen:
            raise ReleaseFormatNotMapped(f"{path.name} repeats series {key}")
        seen.add(key)
        for index, month in months.items():
            if (value := row[index]) is None:
                continue
            if not isinstance(value, int | float):
                raise ReleaseFormatNotMapped(f"{path.name}: non-numeric {value!r} in {key}")
            records.append((month, *key, float(value)))
    if len(seen) != EXPECTED_SERIES:
        raise ReleaseFormatNotMapped(
            f"{path.name} has {len(seen)} series, expected {EXPECTED_SERIES}"
        )

    frame = pd.DataFrame(records, columns=COLUMNS)
    # Totals start in 2002, current-price categories in 2005 and constant-price ones in 2008.
    common_start = frame.groupby(SERIES_KEY)["month"].min().max()
    return frame[frame["month"] >= common_start].reset_index(drop=True)


def _series_key(row: tuple, position: dict, file_name: str) -> tuple[str, str, str]:
    source, unit, frequency = (row[position[h]] for h in ("H01", "H17", "H25"))
    if (source, unit, frequency) != ("P6242_1", "R million", "Monthly"):
        raise ReleaseFormatNotMapped(
            f"{file_name}: unexpected source, unit or frequency: {source}, {unit}, {frequency}"
        )
    label = row[position["H05"]]
    is_total = row[position["H04"]] == "Total"
    category = "total" if is_total else CATEGORY_BY_LABEL.get(label)
    price = PRICE_BY_LABEL.get(row[position["H15"]])
    adjustment = ADJUSTMENT_BY_LABEL.get(row[position["H16"]])
    if category is None or price is None or adjustment is None:
        labels = (label, row[position["H15"]], row[position["H16"]])
        raise ReleaseFormatNotMapped(f"{file_name}: unknown series labels: {labels}")
    return category, price, adjustment


def validate_retail(frame: pd.DataFrame) -> pd.DataFrame:
    """Enforce the silver contract, raising on the first broken rule."""
    missing = set(COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    frame = frame[COLUMNS].copy()
    frame["month"] = pd.to_datetime(frame["month"])

    if frame[COLUMNS].isna().any().any():
        raise ValueError("Retail data has null values")
    if not (frame["month"].dt.day == 1).all():
        raise ValueError("Retail months must be the first day of the month")
    if unknown := set(frame["price_basis"]) - PRICE_BASES:
        raise ValueError(f"Unknown price_basis: {sorted(unknown)}")
    if unknown := set(frame["adjustment"]) - ADJUSTMENTS:
        raise ValueError(f"Unknown adjustment: {sorted(unknown)}")
    if (frame["value_rmillion"] <= 0).any():
        raise ValueError("Retail sales must be positive")
    if frame.duplicated(["month", *SERIES_KEY]).any():
        raise ValueError("Retail data has duplicate series-months")

    # Growth decomposition needs both price bases for every unadjusted month.
    unadjusted = frame[frame["adjustment"] == "unadjusted"]
    if set(unadjusted["price_basis"]) != PRICE_BASES:
        raise ValueError("Unadjusted data must include current and constant prices")
    for key, series in frame.groupby(SERIES_KEY):
        expected = pd.date_range(series["month"].min(), series["month"].max(), freq="MS")
        if len(series) != len(expected):
            raise ValueError(f"Month gap in series {key}")

    bases = unadjusted.groupby(["month", "category"])["price_basis"].nunique()
    if (bases != 2).any():
        raise ValueError("Each unadjusted month needs both current and constant prices")

    _check_total_reconciles(unadjusted)
    frame["month"] = frame["month"].dt.date
    return frame


def _check_total_reconciles(unadjusted: pd.DataFrame) -> None:
    is_total = unadjusted["category"] == "total"
    if not is_total.any():
        raise ValueError("Retail data needs a 'total' category to reconcile against")
    keys = ["month", "price_basis"]
    total = unadjusted[is_total].set_index(keys)["value_rmillion"]
    parts = unadjusted[~is_total].groupby(keys)["value_rmillion"].sum()
    difference = ((parts - total).abs() / total).dropna()
    if (difference > TOTAL_TOLERANCE).any():
        raise ValueError(f"Categories differ from total by up to {difference.max():.2%}")


def write_silver(root: Path, frame: pd.DataFrame) -> Path:
    silver = root / "silver"
    silver.mkdir(parents=True, exist_ok=True)
    path = silver / "retail_trade.parquet"
    validate_retail(frame).to_parquet(path, index=False)
    return path


def run(root: Path) -> Path | None:
    stored = land_release(root)
    if stored is None:
        print(
            f"No workbook in {landing_dir(root)}.\n"
            "Download the P6242.1 time series from statssa.gov.za in a browser and save it there.",
            file=sys.stderr,
        )
        return None
    return write_silver(root, parse_release(stored.path))


if __name__ == "__main__":
    silver_path = run(data_dir())
    if silver_path is None:
        raise SystemExit(2)
    print(f"Retail: wrote {silver_path}")
