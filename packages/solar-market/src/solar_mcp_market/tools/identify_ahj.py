"""identify_ahj: authority-having-jurisdiction + adopted codes for a point.

The SunSpec AHJ Registry needs a token issued by email; without one this tool
degrades gracefully into setup instructions (spec requirement) rather than a
crash or a silent empty result.
"""

from solar_mcp_core import units
from solar_mcp_core.config import api_key_for
from solar_mcp_core.envelope import ToolResult
from solar_mcp_core.errors import SourceUnavailable
from solar_mcp_core.http import SolarHttpClient, freshness_warnings, source_ref
from solar_mcp_core.validation import validate_lat_lon

from solar_mcp_market import api

TOKEN_INSTRUCTIONS = (
    "AHJ Registry token not configured. Request one by emailing support@sunspec.org, "
    "then set AHJ_REGISTRY_TOKEN in the environment. Access is throttled; responses "
    "are cached for 90 days."
)


async def identify_ahj(client: SolarHttpClient, *, lat: float, lon: float) -> ToolResult:
    validate_lat_lon(lat, lon)
    if api_key_for(client.config) is None:
        raise SourceUnavailable(client.config.name, TOKEN_INSTRUCTIONS)

    result = await api.ahj_lookup(client, lat=lat, lon=lon)
    if not result.results:
        raise SourceUnavailable(client.config.name, f"no AHJ found for ({lat}, {lon})")

    ahjs = [record.model_dump() for record in result.results]

    return ToolResult(
        data={"ahjs": ahjs, "ahj_count": len(ahjs)},
        units={
            "ahjs[].name": units.LABEL,
            "ahjs[].level": units.LABEL,
            "ahjs[].building_code": units.LABEL,
            "ahjs[].electric_code": units.LABEL,
            "ahjs[].fire_code": units.LABEL,
            "ahjs[].residential_code": units.LABEL,
            "ahj_count": units.COUNT,
        },
        source=source_ref("SunSpec AHJ Registry", result.fetched, client.config.license_note),
        assumptions=["adopted code editions as registered with SunSpec; verify locally"],
        warnings=freshness_warnings(result.fetched),
    )
