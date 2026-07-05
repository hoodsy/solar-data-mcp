"""MCP resources: provenance agents can cite (license, coverage) per source."""

from mcp.server.fastmcp import FastMCP

USPVDB_LICENSE = """\
USGS/LBNL United States Large-Scale Solar Photovoltaic Database (USPVDB).

- Access: open REST API (no key), https://energy.usgs.gov/uspvdb/
- U.S. federal data: public domain. Cite USGS/LBNL USPVDB and the retrieval
  date; attributes derive from EIA-860 filings and imagery digitization.
"""

TTS_LICENSE = """\
LBNL Tracking the Sun — installed distributed PV system records.

- Access: public data file releases from https://emp.lbl.gov/tracking-the-sun
- Cached locally per user via sync_tracking_the_sun; never re-hosted. This
  server returns aggregate statistics only, not row-level records.
- Cite "Berkeley Lab, Tracking the Sun" and the snapshot vintage.
"""

SOLARTRACE_LICENSE = """\
NREL SolarTRACE — permitting, inspection, and interconnection timelines.

- Access: public dataset downloads from https://maps.nlr.gov/solarTRACE/
- Cached locally per user via sync_solartrace; cite NREL SolarTRACE and the
  snapshot vintage reported in every result.
"""

AHJ_LICENSE = """\
SunSpec AHJ Registry — jurisdictions and adopted code editions.

- Access: token issued by email (support@sunspec.org); throttled. Responses
  are cached for 90 days because AHJ boundaries change rarely.
- This client's request shape follows the public docs but is unverified
  against the live registry (token-gated); confirm results before relying
  on them for filings.
- Verify code editions with the jurisdiction before filing.
"""

COVERAGE = """\
Coverage notes for the solar-market server.

- USPVDB: US ground-mounted facilities >= ~1 MW; updated quarterly.
- Tracking the Sun: distributed PV in participating states/utilities —
  substantial but not complete US coverage; check system_count before
  leaning on small-sample medians.
- SolarTRACE: residential permitting timelines for covered jurisdictions
  (~65% of US residential installs); absence of a jurisdiction is not
  evidence of anything.
- AHJ Registry: US jurisdictions as registered with SunSpec.
"""


def register(mcp: FastMCP) -> None:
    @mcp.resource("source://uspvdb/license", title="USPVDB license & citation")
    def uspvdb_license() -> str:
        return USPVDB_LICENSE

    @mcp.resource("source://tts/license", title="Tracking the Sun license & citation")
    def tts_license() -> str:
        return TTS_LICENSE

    @mcp.resource("source://solartrace/license", title="SolarTRACE license & citation")
    def solartrace_license() -> str:
        return SOLARTRACE_LICENSE

    @mcp.resource("source://ahj/license", title="AHJ Registry access & citation")
    def ahj_license() -> str:
        return AHJ_LICENSE

    @mcp.resource("source://solar-market/coverage", title="Market data coverage & limits")
    def coverage() -> str:
        return COVERAGE
