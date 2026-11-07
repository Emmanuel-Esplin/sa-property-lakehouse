"""The SARB series this project reads, in one place.

Standard library only: the Lambda, the local pipeline and the Glue job all import this list, so a
series is added or changed once.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SarbSeries:
    """One SARB time series and the name it goes by in the lake."""

    code: str
    """SARB's time series code."""
    dataset: str
    """The bronze folder and the `series` value in silver."""
    described_as: str
    """Text SARB's description must contain. If it changes, the measure may have changed too."""


CPI = SarbSeries("CPI1000F", "cpi", "12-Term % change")

RATES = (
    SarbSeries("MMRD002A", "repo_rate", "Policy Rate"),
    SarbSeries("MMRD000A", "prime_rate", "lend"),
    SarbSeries("CMJD004A", "govt_bond_10y_plus", "10 years"),
)

ALL = (CPI, *RATES)
