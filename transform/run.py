"""Run the dbt project, locally on DuckDB or in AWS on Athena.

dbt runs as a subprocess. Run in-process, dbt-duckdb can keep the warehouse file open, and later
read-only connections then fail.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from ingestion.common.bronze import data_dir

PROJECT_DIR = Path(__file__).parent
DBT = Path(sys.executable).parent / "dbt"
ANSI_COLOUR = re.compile(r"\x1b\[[0-9;]*m")
SUMMARY_LINES = 30


class DbtFailed(RuntimeError):
    """dbt finished with a failed model or test. The message holds dbt's summary."""


def dbt(root: Path, command: list[str], target: str = "local") -> str:
    """Run one dbt command. Its files and logs go under the data folder, not the repo."""
    env = {
        **os.environ,
        "LAKEHOUSE_DATA_DIR": str(root),
        "DBT_TARGET_PATH": str(root / "dbt" / "target"),
        "DBT_LOG_PATH": str(root / "dbt" / "logs"),
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
    }
    result = subprocess.run(
        [
            str(DBT),
            *command,
            "--project-dir",
            str(PROJECT_DIR),
            "--profiles-dir",
            str(PROJECT_DIR),
            "--target",
            target,
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # dbt ends with a summary of what failed and why, so keep its last lines whole.
        output = ANSI_COLOUR.sub("", result.stdout + result.stderr).strip().splitlines()
        raise DbtFailed("\n".join(output[-SUMMARY_LINES:]))
    return result.stdout


def build(root: Path) -> Path:
    """Seed, build and test every model locally. Returns the warehouse path."""
    silver = root / "silver"
    inputs = ("retail_trade.parquet", "cpi.parquet", "rates.parquet")
    for name in inputs:
        if not (silver / name).exists():
            raise FileNotFoundError(f"Missing {silver / name}. Run `make all`.")
    (root / "gold").mkdir(parents=True, exist_ok=True)
    dbt(root, ["build"])
    return root / "gold" / "warehouse.duckdb"


def _require_bucket() -> None:
    if not os.environ.get("LAKE_BUCKET"):
        raise RuntimeError("Set LAKE_BUCKET, or use `make dbt-athena`, which sets it for you.")


def build_athena(root: Path) -> None:
    """Seed, build and test every model on Athena, reading the silver Iceberg tables."""
    _require_bucket()
    dbt(root, ["build"], target="athena")


def export_athena(root: Path) -> None:
    """Unload the Athena marts to S3 as Parquet, so they can be compared locally."""
    _require_bucket()
    dbt(root, ["run-operation", "export_marts"], target="athena")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["local", "athena"], default="local")
    parser.add_argument("--export", action="store_true", help="Athena only: unload marts to S3")
    args = parser.parse_args()
    root = data_dir()
    if args.export and args.target != "athena":
        parser.error("--export needs --target athena")
    if args.export:
        export_athena(root)
        print(f"Exported the Athena marts to s3://{os.environ['LAKE_BUCKET']}/exports/dbt/")
    elif args.target == "athena":
        build_athena(root)
        print("Built and tested the marts on Athena")
    else:
        print(f"Built and tested {build(root)}")
