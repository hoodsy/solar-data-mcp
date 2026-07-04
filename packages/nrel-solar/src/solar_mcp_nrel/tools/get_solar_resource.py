"""get_solar_resource: annual/monthly irradiance statistics for a location."""

from typing import Any

from solar_mcp_core import units
from solar_mcp_core.envelope import ToolResult
from solar_mcp_core.errors import SourceUnavailable
from solar_mcp_core.http import SolarHttpClient

from solar_mcp_nrel import api
from solar_mcp_nrel.models import validate_coords
from solar_mcp_nrel.tools._envelope import freshness_warnings, source_ref

CELL_ASSUMPTION = (
    "NSRDB solar-resource cells are 0.1 deg (~10 km); resolved cell center is "
    "computed from grid geometry — the API does not return it."
)


def resolved_cell(lat: float, lon: float) -> tuple[float, float]:
    """Center of the 0.1-degree grid cell containing the query point."""
    return round(lat, 1), round(lon, 1)


async def get_solar_resource(client: SolarHttpClient, *, lat: float, lon: float) -> ToolResult:
    validate_coords(lat, lon)
    result = await api.solar_resource(client, lat, lon)
    outputs = result.response.outputs
    if outputs is None or (outputs.avg_ghi is None and outputs.avg_dni is None):
        raise SourceUnavailable(
            client.config.name,
            f"no solar resource data at ({lat}, {lon}) — NSRDB coverage is the "
            "Americas; international sites are not supported",
        )

    warnings = [*result.response.warnings, *freshness_warnings(result.fetched)]
    cell_lat, cell_lon = resolved_cell(lat, lon)

    data: dict[str, Any] = {
        "resolved_cell_lat": cell_lat,
        "resolved_cell_lon": cell_lon,
    }
    unit_map: dict[str, str] = {
        "resolved_cell_lat": units.DEGREES,
        "resolved_cell_lon": units.DEGREES,
    }
    for label, series in (("ghi", outputs.avg_ghi), ("dni", outputs.avg_dni)):
        if series is None:
            warnings.append(f"{label.upper()} not available for this location")
            continue
        data[f"{label}_annual"] = series.annual
        data[f"{label}_monthly"] = series.monthly
        unit_map[f"{label}_annual"] = units.KWH_PER_M2_DAY
        unit_map[f"{label}_monthly"] = units.KWH_PER_M2_DAY

    return ToolResult(
        data=data,
        units=unit_map,
        source=source_ref("NREL Solar Resource v1 (NSRDB)", result.fetched),
        assumptions=[CELL_ASSUMPTION],
        warnings=warnings,
    )
