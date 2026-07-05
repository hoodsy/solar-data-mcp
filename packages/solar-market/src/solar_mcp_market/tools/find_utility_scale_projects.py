"""find_utility_scale_projects: USPVDB facilities by state or bounding box."""

from typing import Any

from solar_mcp_core import units
from solar_mcp_core.envelope import ToolResult
from solar_mcp_core.errors import BadInput, SourceUnavailable
from solar_mcp_core.http import SolarHttpClient, freshness_warnings, source_ref
from solar_mcp_core.validation import validate_state

from solar_mcp_market import api
from solar_mcp_market.models import validate_bbox

MAX_LIMIT = 100


async def find_utility_scale_projects(
    client: SolarHttpClient,
    *,
    state: str | None = None,
    bbox: list[float] | None = None,
    min_capacity_mw: float | None = None,
    limit: int | None = None,
) -> ToolResult:
    assumptions: list[str] = []
    if (state is None) == (bbox is None):
        raise BadInput(
            field="state | bbox",
            value=f"state={state}, bbox={bbox}",
            allowed="exactly one of state or bbox=[west, south, east, north]",
        )
    if state is not None:
        state = validate_state(state)
    box = validate_bbox(bbox) if bbox is not None else None
    if min_capacity_mw is not None and min_capacity_mw < 0:
        raise BadInput(field="min_capacity_mw", value=min_capacity_mw, allowed=">= 0")
    if limit is None:
        limit = 25
        assumptions.append("limit not provided; defaulted to 25 (largest first)")
    if not 1 <= limit <= MAX_LIMIT:
        raise BadInput(field="limit", value=limit, allowed=f"1 to {MAX_LIMIT}")

    result = await api.uspvdb_projects(
        client, state=state, bbox=box, min_capacity_mw=min_capacity_mw, limit=limit
    )
    if not result.projects:
        where = state if state is not None else f"bbox {bbox}"
        raise SourceUnavailable(
            client.config.name,
            f"no utility-scale projects found for {where}"
            + (f" at >= {min_capacity_mw} MW-AC" if min_capacity_mw else ""),
        )

    projects: list[dict[str, Any]] = [
        {
            "name": p.p_name,
            "state": p.p_state,
            "county": p.p_county,
            "year": p.p_year,
            "capacity_mw_ac": p.p_cap_ac,
            "capacity_mw_dc": p.p_cap_dc,
            "lat": p.ylat,
            "lon": p.xlong,
            "tracking": p.p_axis,
            "has_battery": p.p_battery == "batteries",
            "eia_id": p.eia_id,
        }
        for p in result.projects
    ]
    total_ac = round(sum(p["capacity_mw_ac"] or 0.0 for p in projects), 1)

    return ToolResult(
        data={
            "projects": projects,
            "project_count": len(projects),
            "total_capacity_mw_ac": total_ac,
        },
        units={
            "projects[].name": units.LABEL,
            "projects[].capacity_mw_ac": units.MW_AC,
            "projects[].capacity_mw_dc": units.MW_DC,
            "projects[].lat": units.DEGREES,
            "projects[].lon": units.DEGREES,
            "projects[].year": units.YEAR,
            "project_count": units.COUNT,
            "total_capacity_mw_ac": units.MW_AC,
        },
        source=source_ref(
            "USGS/LBNL US Large-Scale Solar Photovoltaic Database (USPVDB)",
            result.fetched,
            client.config.license_note,
        ),
        assumptions=[
            *assumptions,
            "ordered by AC capacity descending; EIA-860-derived attributes",
        ],
        warnings=freshness_warnings(result.fetched),
    )
