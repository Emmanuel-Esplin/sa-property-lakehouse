"""JSE REIT prices and distributions, from CSV files a person downloads and saves.

The project defines its own simple format, so any source the user is allowed to use can feed it:
export to the format and save the files in the landing folder. The checks are strict, because a
wrong unit or a missing stretch of prices quietly distorts every return built on top.

The files in the landing folder are the current data. Bronze keeps every version as history.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ingestion.common.bronze import REPO_ROOT, data_dir, write_bronze

SEED = REPO_ROOT / "transform" / "seeds" / "reits.csv"

# JSE prices are quoted in cents. A price in rand mixed in moves by a factor of 100 in a day.
MAX_DAILY_MOVE = 0.5
# Longer than any JSE holiday break, short enough to catch a missing stretch of prices.
MAX_GAP_DAYS = 14


@dataclass(frozen=True)
class FileKind:
    """One kind of landed file, and how its rows map onto silver."""

    name: str
    """The landing folder and bronze dataset."""
    columns: list[str]
    """The exact header a landed CSV must have."""
    date_column: str
    value_column: str
    silver: pa.Schema
    """Explicit, so an empty silver file still has the column types dbt expects."""


PRICES = FileKind(
    name="prices",
    columns=["date", "ticker", "close_cents"],
    date_column="date",
    value_column="close_cents",
    silver=pa.schema(
        [("price_date", pa.date32()), ("ticker", pa.string()), ("close_cents", pa.float64())]
    ),
)
DISTRIBUTIONS = FileKind(
    name="distributions",
    columns=["ticker", "ex_date", "amount_cents"],
    date_column="ex_date",
    value_column="amount_cents",
    silver=pa.schema(
        [("ex_date", pa.date32()), ("ticker", pa.string()), ("amount_cents", pa.float64())]
    ),
)


def landing_dir(root: Path, kind: FileKind) -> Path:
    """Where a person saves one kind of file."""
    return root / "landing" / "market" / kind.name


def known_tickers() -> set[str]:
    """Tickers listed in the seed. Each needs a sector, so unknown tickers are refused."""
    return set(pd.read_csv(SEED)["ticker"])


def read_landed(root: Path, kind: FileKind) -> pd.DataFrame:
    """Copy every landed CSV to bronze and return all their rows, typed but not yet checked."""
    folder = landing_dir(root, kind)
    folder.mkdir(parents=True, exist_ok=True)
    frames = []
    for path in sorted(folder.rglob("*.csv")):
        content = path.read_bytes()
        if b"<html" in content[:1024].lower():
            raise ValueError(f"{path.name} is an HTML page, not a CSV file. Download it again.")
        stored = write_bronze(root, "market", kind.name, path.name, content, f"manual:{path}")
        # Read every cell as text. Left to itself, pandas turns "n/a" or "-" into NaN, and the
        # error would then show "nan" instead of what is actually in the file.
        frame = pd.read_csv(stored.path, dtype=str, keep_default_na=False, skipinitialspace=True)
        if list(frame.columns) != kind.columns:
            raise ValueError(
                f"{path.name}: columns must be {kind.columns}, not {list(frame.columns)}"
            )
        frames.append(_typed(frame.assign(source_file=path.name), kind))
    if not frames:
        return pd.DataFrame(columns=[*kind.columns, "source_file"])
    return pd.concat(frames, ignore_index=True)


def _typed(frame: pd.DataFrame, kind: FileKind) -> pd.DataFrame:
    """Parse dates and numbers, naming the file and value of the first one that won't parse."""
    frame["ticker"] = frame["ticker"].str.strip().str.upper()
    dates = pd.to_datetime(frame[kind.date_column], format="%Y-%m-%d", errors="coerce")
    values = pd.to_numeric(frame[kind.value_column], errors="coerce")
    for column, parsed in ((kind.date_column, dates), (kind.value_column, values)):
        if parsed.isna().any():
            row = frame[parsed.isna()].iloc[0]
            raise ValueError(f"{row['source_file']}: {column} {row[column]!r} is not valid")
    frame[kind.date_column] = dates
    frame[kind.value_column] = values
    return frame


def _drop_repeats(frame: pd.DataFrame, kind: FileKind) -> pd.DataFrame:
    """Overlapping downloads repeat rows: identical ones are dropped, conflicting ones refused."""
    frame = frame.drop_duplicates(subset=kind.columns)
    key = ["ticker", kind.date_column]
    conflicts = frame[frame.duplicated(subset=key, keep=False)]
    if not conflicts.empty:
        first = conflicts.sort_values(key).iloc[0]
        raise ValueError(
            f"Conflicting {kind.value_column} for {first['ticker']} on "
            f"{first[kind.date_column].date()} in {sorted(set(conflicts['source_file']))}"
        )
    return frame


def validate_prices(frame: pd.DataFrame, tickers: set[str]) -> pd.DataFrame:
    """Enforce the price contract and return silver rows: price_date, ticker, close_cents."""
    frame = _drop_repeats(frame, PRICES).sort_values(["ticker", "date"], ignore_index=True)
    if unknown := set(frame["ticker"]) - tickers:
        raise ValueError(
            f"Unknown tickers {sorted(unknown)}: add them to {SEED.name} with a sector"
        )
    if (frame["close_cents"] <= 0).any():
        raise ValueError("Prices must be positive")

    by_ticker = frame.groupby("ticker")
    gaps = by_ticker["date"].diff().dt.days
    if (gaps > MAX_GAP_DAYS).any():
        row = frame[gaps > MAX_GAP_DAYS].iloc[0]
        raise ValueError(
            f"{row['ticker']} has no prices in the {gaps.max():.0f} days before "
            f"{row['date'].date()}. Missing prices would distort its returns."
        )
    moves = by_ticker["close_cents"].pct_change().abs()
    if (moves > MAX_DAILY_MOVE).any():
        row = frame[moves > MAX_DAILY_MOVE].iloc[0]
        raise ValueError(
            f"{row['ticker']} moved {moves.max():.0%} on {row['date'].date()}. "
            "Check for prices in rand mixed with prices in cents."
        )

    return pd.DataFrame(
        {
            "price_date": frame["date"].dt.date,
            "ticker": frame["ticker"],
            "close_cents": frame["close_cents"],
        }
    )


def validate_distributions(frame: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Enforce the distribution contract. Each must fall within its REIT's price history."""
    frame = _drop_repeats(frame, DISTRIBUTIONS)
    if (frame["amount_cents"] <= 0).any():
        raise ValueError("Distributions must be positive")

    # A distribution outside the price history can't enter any return, so it is likely a typo.
    span = prices.groupby("ticker")["price_date"].agg(["min", "max"])
    for row in frame.itertuples():
        if row.ticker not in span.index:
            raise ValueError(
                f"{row.source_file}: distribution for {row.ticker}, which has no prices"
            )
        first, last = span.loc[row.ticker]
        if not first <= row.ex_date.date() <= last:
            raise ValueError(
                f"{row.ticker} distribution on {row.ex_date.date()} is outside its prices "
                f"({first} to {last})"
            )

    return pd.DataFrame(
        {
            "ex_date": frame["ex_date"].dt.date,
            "ticker": frame["ticker"],
            "amount_cents": frame["amount_cents"],
        }
    )


def write_silver(root: Path, kind: FileKind, frame: pd.DataFrame) -> Path:
    """Write one silver file with its fixed schema, even when there are no rows."""
    silver = root / "silver"
    silver.mkdir(parents=True, exist_ok=True)
    path = silver / f"reit_{kind.name}.parquet"
    pq.write_table(pa.Table.from_pandas(frame, schema=kind.silver, preserve_index=False), path)
    return path


def run(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Check every landed file, then write both silver files. With no files, both are empty."""
    raw_prices = read_landed(root, PRICES)
    raw_distributions = read_landed(root, DISTRIBUTIONS)

    prices = (
        validate_prices(raw_prices, known_tickers()) if len(raw_prices) else empty_frame(PRICES)
    )
    distributions = (
        validate_distributions(raw_distributions, prices)
        if len(raw_distributions)
        else empty_frame(DISTRIBUTIONS)
    )
    # Both kinds are checked before either is written, so silver never mixes old and new data.
    write_silver(root, PRICES, prices)
    write_silver(root, DISTRIBUTIONS, distributions)
    return prices, distributions


def empty_frame(kind: FileKind) -> pd.DataFrame:
    """No rows, in the silver schema. Used when nothing has landed yet."""
    return kind.silver.empty_table().to_pandas()


if __name__ == "__main__":
    reit_prices, reit_distributions = run(data_dir())
    if reit_prices.empty:
        print(
            f"No REIT files in {landing_dir(data_dir(), PRICES).parent}, so the REIT marts will be "
            "empty. See docs/market-data-format.md.",
            file=sys.stderr,
        )
    else:
        print(
            f"REITs: {reit_prices['ticker'].nunique()} tickers, {len(reit_prices)} prices, "
            f"{len(reit_distributions)} distributions"
        )
