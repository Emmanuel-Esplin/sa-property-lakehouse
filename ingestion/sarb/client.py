"""Standard-library client for the SARB web API, small enough to run in Lambda without layers."""

import time
import urllib.error
import urllib.request

API = "https://custom.resbank.co.za/SarbWebApi/WebIndicators/Shared/GetTimeseriesObservations"
START_DATE = "2000-01-01"
USER_AGENT = "sa-property-lakehouse/0.1"


def fetch_series(code: str, start: str, end: str, attempts: int = 3) -> bytes:
    """Return the raw JSON for one series, retrying network errors with a growing pause."""
    url = f"{API}/{code}/{start}/{end}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                content_type = response.headers.get("Content-Type", "")
                body = response.read()
            # A block page or error page arrives as HTML with status 200, so check the type.
            if "json" not in content_type:
                raise ValueError(f"Expected JSON from {url}, got {content_type!r}")
            return body
        except urllib.error.URLError:
            if attempt == attempts:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")
