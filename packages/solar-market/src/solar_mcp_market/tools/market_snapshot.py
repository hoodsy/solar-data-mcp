"""market_snapshot: one-call composite of installs, prices, timelines, pipeline."""

from typing import Any

from solar_mcp_core import units
from solar_mcp_core.bulk import BulkStore
from solar_mcp_core.envelope import ToolResult, audit_entry, composite_source_ref
from solar_mcp_core.errors import SolarMCPError, SourceUnavailable
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_core.validation import validate_state

from solar_mcp_market.tools.find_utility_scale_projects import find_utility_scale_projects
from solar_mcp_market.tools.get_permitting_timelines import get_permitting_timelines
from solar_mcp_market.tools.query_installed_systems import query_installed_systems


async def market_snapshot(
    uspvdb_client: SolarHttpClient, store: BulkStore, *, state: str
) -> ToolResult:
    """Best-effort composite: each section fills in if its source is available."""
    state = validate_state(state)
    data: dict[str, Any] = {"state": state}
    unit_map: dict[str, str] = {"state": units.LABEL}
    assumptions: list[str] = []
    warnings: list[str] = []
    audit: list[dict[str, str]] = []
    sections = 0

    try:
        installs = await query_installed_systems(store, state=state)
        data["installed_systems"] = installs.data
        unit_map.update({f"installed_systems.{k}": v for k, v in installs.units.items()})
        assumptions.extend(f"installed_systems: {a}" for a in installs.assumptions)
        audit.append(audit_entry("installed_systems", installs.source))
        sections += 1
    except SolarMCPError as exc:
        warnings.append(f"installed_systems unavailable: {exc}")

    try:
        timelines = await get_permitting_timelines(store, state=state)
        data["permitting"] = {
            k: timelines.data[k]
            for k in ("median_permit_days", "median_inspection_days", "median_pto_days")
        }
        unit_map.update({f"permitting.{k}": units.DAYS for k in data["permitting"]})
        assumptions.extend(f"permitting: {a}" for a in timelines.assumptions)
        audit.append(audit_entry("permitting", timelines.source))
        sections += 1
    except SolarMCPError as exc:
        warnings.append(f"permitting unavailable: {exc}")

    try:
        pipeline = await find_utility_scale_projects(uspvdb_client, state=state, limit=5)
        data["utility_scale"] = {
            "largest_projects": [
                {"name": p["name"], "capacity_mw_ac": p["capacity_mw_ac"], "year": p["year"]}
                for p in pipeline.data["projects"]
            ],
            "total_capacity_mw_ac_top5": pipeline.data["total_capacity_mw_ac"],
        }
        unit_map.update(
            {
                "utility_scale.largest_projects[].name": units.LABEL,
                "utility_scale.largest_projects[].capacity_mw_ac": units.MW_AC,
                "utility_scale.largest_projects[].year": units.YEAR,
                "utility_scale.total_capacity_mw_ac_top5": units.MW_AC,
            }
        )
        audit.append(audit_entry("utility_scale", pipeline.source))
        sections += 1
    except SolarMCPError as exc:
        warnings.append(f"utility_scale unavailable: {exc}")

    if sections == 0:
        raise SourceUnavailable(
            "solar-market",
            f"no market data available for {state}: sync the bulk datasets and/or "
            "check USPVDB connectivity (see warnings for each failure)",
        )

    data["audit_trail"] = audit
    unit_map.update(
        {"audit_trail[].component": units.LABEL, "audit_trail[].retrieved_at": units.ISO_DATE}
    )
    return ToolResult(
        data=data,
        units=unit_map,
        source=composite_source_ref(),
        assumptions=assumptions or ["all sections best-effort; see audit_trail for sources"],
        warnings=warnings,
    )
