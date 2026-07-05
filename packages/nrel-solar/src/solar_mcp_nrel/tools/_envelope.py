"""NREL-specific envelope pieces; generic recipes live in core.http."""

from solar_mcp_core.envelope import SourceRef
from solar_mcp_core.http import FetchedResponse, freshness_warnings
from solar_mcp_core.http import source_ref as _core_source_ref

__all__ = ["NREL_LICENSE", "PVWATTS_CAVEAT", "freshness_warnings", "source_ref"]

PVWATTS_CAVEAT = (
    "PVWatts models a typical system from TMY weather data; estimates do not "
    "reflect site-specific shading, snow, soiling, or module-level differences. "
    "Actual production commonly varies +/-10% year to year."
)

NREL_LICENSE = "NREL Developer Network (free, attribution appreciated)"


def source_ref(name: str, fetched: FetchedResponse) -> SourceRef:
    return _core_source_ref(name, fetched, NREL_LICENSE)
