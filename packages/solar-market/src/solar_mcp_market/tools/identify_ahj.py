"""identify_ahj: authority-having-jurisdiction + adopted codes for a point.

The SunSpec AHJ Registry needs a token issued by email; without one this tool
degrades gracefully into setup instructions (spec requirement) rather than a
crash or a silent empty result.
"""

from typing import Any

from solar_mcp_core import units
from solar_mcp_core.config import AHJ, api_key_for
from solar_mcp_core.envelope import ToolResult
from solar_mcp_core.errors import BadInput, SourceUnavailable
from solar_mcp_core.http import SolarHttpClient, freshness_warnings, source_ref

from solar_mcp_market import api

TOKEN_INSTRUCTIONS = (
    "AHJ Registry token not configured. Request one by emailing support@sunspec.org, "
    "then set AHJ_REGISTRY_TOKEN in the environment. Access is throttled; responses "
    "are cached for 90 days."
)

_CODE_FIELDS = (
    ("building_code", "BuildingCode"),
    ("electric_code", "ElectricCode"),
    ("fire_code", "FireCode"),
    ("residential_code", "ResidentialCode"),
)


async def identify_ahj(client: SolarHttpClient, *, lat: float, lon: float) -> ToolResult:
    if not -90 <= lat <= 90:
        raise BadInput(field="lat", value=lat, allowed="-90 to 90")
    if not -180 <= lon <= 180:
        raise BadInput(field="lon", value=lon, allowed="-180 to 180")
    if api_key_for(AHJ) is None:
        raise SourceUnavailable(AHJ.name, TOKEN_INSTRUCTIONS)

    result = await api.ahj_lookup(client, lat=lat, lon=lon)
    if not result.results:
        raise SourceUnavailable(AHJ.name, f"no AHJ found for ({lat}, {lon})")

    ahjs: list[dict[str, Any]] = []
    for raw in result.results:
        entry: dict[str, Any] = {
            "name": raw.get("AHJName"),
            "level": raw.get("AHJLevelCode"),
        }
        for out_field, in_field in _CODE_FIELDS:
            entry[out_field] = raw.get(in_field)
        ahjs.append(entry)

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
        source=source_ref("SunSpec AHJ Registry", result.fetched, AHJ.license_note),
        assumptions=["adopted code editions as registered with SunSpec; verify locally"],
        warnings=freshness_warnings(result.fetched),
    )
