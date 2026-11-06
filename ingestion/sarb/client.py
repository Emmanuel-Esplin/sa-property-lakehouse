"""Standard-library client for the SARB web API, small enough to run in Lambda without layers."""

import time
import urllib.error
import urllib.request

API = "https://custom.resbank.co.za/SarbWebApi/WebIndicators/Shared/GetTimeseriesObservations"
CPI_SERIES = "CPI1000F"
START_DATE = "2000-01-01"
USER_AGENT = "sa-property-lakehouse/0.1"


def fetch_series(code: str, start: str, end: str, attempts: int = 3) -> bytes:
    url = f"{API}/{code}/{start}/{end}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                content_type = response.headers.get("Content-Type", "")
                body = response.read()
            if "json" not in content_type:
                raise ValueError(f"Expected JSON from {url}, got {content_type!r}")
            return body
        except urllib.error.URLError:
            if attempt == attempts:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")
