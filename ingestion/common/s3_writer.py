"""Bronze layer on S3: one immutable object per unique file, with provenance in its metadata."""

import hashlib
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath


@dataclass(frozen=True)
class BronzeObject:
    key: str
    sha256: str
    is_new: bool


def put_bronze(
    client, bucket: str, source: str, dataset: str, name: str, content: bytes, origin: str
) -> BronzeObject:
    """Write content once per hash. If-None-Match makes a repeat a no-op, even in a race."""
    sha256 = hashlib.sha256(content).hexdigest()
    # The hash alone names the object, so a renamed copy of a file is still the same object.
    original_name = PurePosixPath(name).name
    key = f"bronze/{source}/{dataset}/{sha256[:12]}{PurePosixPath(name).suffix}"
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            IfNoneMatch="*",
            Metadata={
                "sha256": sha256,
                # S3 metadata must be ASCII, and file names may not be.
                "original-name": urllib.parse.quote(original_name),
                "origin": urllib.parse.quote(origin, safe="/:"),
                "retrieved-at": datetime.now(UTC).isoformat(timespec="seconds"),
            },
        )
    except Exception as error:
        code = getattr(error, "response", {}).get("Error", {}).get("Code")
        if code != "PreconditionFailed":
            raise
        return BronzeObject(key, sha256, is_new=False)
    return BronzeObject(key, sha256, is_new=True)
