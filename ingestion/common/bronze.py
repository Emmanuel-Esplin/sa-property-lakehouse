"""Bronze layer: immutable, content-addressed copies of source files, with provenance."""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    """The lake's root folder. Tests point LAKEHOUSE_DATA_DIR at a temporary folder."""
    return Path(os.environ.get("LAKEHOUSE_DATA_DIR", REPO_ROOT / "data"))


@dataclass(frozen=True)
class BronzeObject:
    """Where a file was stored, and whether this call stored it or found it already there."""

    path: Path
    sha256: str
    is_new: bool


def write_bronze(
    root: Path, source: str, dataset: str, name: str, content: bytes, origin: str
) -> BronzeObject:
    """Store content once per unique hash and record where it came from in a manifest.

    Keeping every vintage matters here: Stats SA revises history and rebases constant prices,
    so a later release is not a superset of an earlier one.
    """
    sha256 = hashlib.sha256(content).hexdigest()
    folder = root / "bronze" / source / dataset
    folder.mkdir(parents=True, exist_ok=True)
    # The hash alone names the file, so a renamed copy of a file is still the same object.
    path = folder / f"{sha256[:12]}{Path(name).suffix}"
    if path.exists():
        return BronzeObject(path, sha256, is_new=False)

    path.write_bytes(content)
    entry = {
        "file": path.name,
        "original_name": name,
        "sha256": sha256,
        "bytes": len(content),
        "origin": origin,
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    with (folder / "manifest.jsonl").open("a") as manifest:
        manifest.write(json.dumps(entry) + "\n")
    return BronzeObject(path, sha256, is_new=True)
