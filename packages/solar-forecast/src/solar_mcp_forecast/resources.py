"""MCP resources: provenance agents can cite (license, coverage)."""

from mcp.server.fastmcp import FastMCP

QUARTZ_LICENSE_TEXT = """\
Quartz Solar Forecast — Open Climate Fix.

- Model and code: MIT license, https://github.com/openclimatefix/quartz-solar-forecast
- Inputs: open numerical weather prediction data; no API key, no live PV feed.
- Cite "Open Climate Fix, Quartz Solar Forecast" with the run timestamp.
"""

COVERAGE = """\
Coverage notes for the solar-forecast server.

- Forecasts are cold-start (weather-only) site-level estimates, horizon <= 48h,
  global NWP coverage; accuracy is best where NWP models are strong (US/EU).
- Screening-grade output: planning and "is today unusual" questions — not for
  grid settlement, bidding, or contractual commitments.
- The comparison baseline is PVWatts TMY (typical meteorological year) spread
  uniformly over the month's hours; see each result's assumptions.
- The quartz-solar-forecast package must be installed separately (its pydantic
  pin conflicts with the MCP SDK — see the package README for the exact steps).
"""


def register(mcp: FastMCP) -> None:
    @mcp.resource("source://quartz/license", title="Quartz model license & citation")
    def quartz_license() -> str:
        return QUARTZ_LICENSE_TEXT

    @mcp.resource("source://solar-forecast/coverage", title="Forecast coverage & limits")
    def coverage() -> str:
        return COVERAGE
