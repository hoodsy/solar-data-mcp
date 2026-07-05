"""MCP resources: provenance agents can cite (license, coverage) per source."""

from mcp.server.fastmcp import FastMCP

OPENEI_LICENSE = """\
OpenEI Utility Rate Database (URDB).

- Access: free API key from https://openei.org/services/api/signup/
- Data license: Creative Commons Attribution (CC-BY); cite "OpenEI Utility
  Rate Database" and the schedule's own uri/source fields.
- Rates are crowd-maintained from utility filings; verify against the linked
  tariff PDF before contractual use.
"""

EIA_LICENSE = """\
U.S. Energy Information Administration API v2.

- Access: free API key from https://www.eia.gov/opendata/register.php
- U.S. federal data: public domain. Cite "U.S. Energy Information
  Administration" and the series (electricity/retail-sales).
"""

DSIRE_LICENSE = """\
DSIRE — Database of State Incentives for Renewables & Efficiency
(NC Clean Energy Technology Center).

- Open path: public bulk snapshots loaded locally via sync_incentives; the
  live API is subscriber-access. Snapshots are cached per-user, never re-hosted.
- Cite DSIRE and the snapshot vintage reported in every get_incentives result.
"""

COVERAGE = """\
Coverage notes for the solar-economics server.

- URDB: US utilities; approved schedules only; time-of-use schedules are
  flagged, not simulated (tier values are approximations for TOU rates).
- EIA retail-sales: US states, monthly, ~2-month publication lag.
- Incentives: federal ITC is hardcoded current law (26 USC §25D) with sunset
  dates; state/local programs require a locally synced DSIRE snapshot and
  cite its vintage.
- estimate_roi is a screening estimate: full retail net-metering credit,
  0.5%/yr degradation, nominal-dollar payback. Never a quote.
"""


def register(mcp: FastMCP) -> None:
    @mcp.resource("source://openei/license", title="URDB data license & citation")
    def openei_license() -> str:
        return OPENEI_LICENSE

    @mcp.resource("source://eia/license", title="EIA data license & citation")
    def eia_license() -> str:
        return EIA_LICENSE

    @mcp.resource("source://dsire/license", title="DSIRE data license & citation")
    def dsire_license() -> str:
        return DSIRE_LICENSE

    @mcp.resource("source://solar-economics/coverage", title="Economics coverage & limits")
    def coverage() -> str:
        return COVERAGE
