"""Shared envelope plumbing for nrel-solar tools."""

from solar_mcp_core.envelope import SourceRef
from solar_mcp_core.http import FetchedResponse

PVWATTS_CAVEAT = (
    "PVWatts models a typical system from TMY weather data; estimates do not "
    "reflect site-specific shading, snow, soiling, or module-level differences. "
    "Actual production commonly varies +/-10% year to year."
)

NREL_LICENSE = "NREL Developer Network (free, attribution appreciated)"


def source_ref(name: str, fetched: FetchedResponse) -> SourceRef:
    return SourceRef(
        name=name,
        url=fetched.url,
        retrieved_at=fetched.retrieved_at,
        license=NREL_LICENSE,
    )


def freshness_warnings(fetched: FetchedResponse) -> list[str]:
    if fetched.stale:
        return [
            "Served from an expired cache entry because the NREL rate limit is "
            "exhausted; values may be out of date."
        ]
    return []
