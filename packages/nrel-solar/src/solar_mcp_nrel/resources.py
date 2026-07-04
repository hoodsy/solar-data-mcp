"""MCP resources: provenance agents can cite (license, coverage)."""

from mcp.server.fastmcp import FastMCP

LICENSE_TEXT = """\
NREL Developer Network data (PVWatts v8, NSRDB Solar Resource).

- Access: free API key from https://developer.nlr.gov/signup/
- Terms: https://developer.nlr.gov/docs/terms/
- Data is produced by the U.S. National Renewable Energy Laboratory and is
  generally public information; attribution to NREL is appreciated.
- Cite: PVWatts v8 (NREL SAM/SSC pvwattsv8); solar resource data from the
  National Solar Radiation Database (NSRDB) and Perez-SUNY/NREL 2012 model.
"""

COVERAGE_TEXT = """\
Coverage notes for the nrel-solar server.

- PVWatts v8 (dataset=nsrdb): NSRDB PSM v3 TMY-2020 weather; covers the
  Americas (US in full). station_info.distance (meters) in each response says
  how far the weather cell is from the requested point; this server warns
  above 32 km.
- Solar Resource v1: Perez-SUNY/NREL 2012 model, 1998-2009 average, 0.1-degree
  (~10 km) cells, US coverage; international locations return an error.
- Rate limit: 1,000 requests/hour per key across ALL developer.nlr.gov APIs
  (rolling window). This server caches responses for 30 days, so repeated
  queries do not consume quota.
"""


def register(mcp: FastMCP) -> None:
    @mcp.resource("source://nrel/license", title="NREL data license & citation")
    def nrel_license() -> str:
        return LICENSE_TEXT

    @mcp.resource("source://nrel/coverage", title="NREL data coverage & limits")
    def nrel_coverage() -> str:
        return COVERAGE_TEXT
