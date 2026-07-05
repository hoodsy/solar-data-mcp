"""estimate_production: annual/monthly AC output for a PV system via PVWatts v8."""

from dataclasses import dataclass
from typing import Any

from solar_mcp_core import units
from solar_mcp_core.envelope import ToolResult
from solar_mcp_core.http import SolarHttpClient, freshness_warnings, source_ref
from solar_mcp_core.validation import default_tilt_azimuth

from solar_mcp_nrel import api
from solar_mcp_nrel.models import PVWattsRequest, SystemSpec, build_pvwatts_request
from solar_mcp_nrel.tools._envelope import PVWATTS_CAVEAT

DEFAULT_ARRAY_TYPE = "fixed_roof"
DEFAULT_MODULE_TYPE = "standard"
DEFAULT_LOSSES_PCT = 14.0
DEFAULT_DC_AC_RATIO = 1.2
DEFAULT_BIFACIALITY = 0.7  # typical mid-range for bifacial modules per PVWatts docs
STATION_DISTANCE_WARN_METERS = 32_000


@dataclass
class ResolvedRequest:
    request: PVWattsRequest
    assumptions: list[str]
    warnings: list[str]


def resolve_request(
    spec: SystemSpec,
    system_capacity_kw: float,
    *,
    bifacial: bool = False,
    albedo: float | None = None,
) -> ResolvedRequest:
    """Fill unspecified spec fields with documented defaults, recording each
    injected value as an assumption. Explicitly-passed values are never
    reported as assumptions. Pure — unit-testable without HTTP."""
    tilt, azimuth, assumptions, warnings = default_tilt_azimuth(
        spec.lat, spec.tilt_deg, spec.azimuth_deg
    )

    array_type = spec.array_type
    if array_type is None:
        array_type = DEFAULT_ARRAY_TYPE
        assumptions.append("array_type not provided; defaulted to fixed_roof (roof mounted)")

    module_type = spec.module_type
    if module_type is None:
        module_type = DEFAULT_MODULE_TYPE
        assumptions.append("module_type not provided; defaulted to standard (crystalline si)")

    losses = spec.losses_pct
    if losses is None:
        losses = DEFAULT_LOSSES_PCT
        assumptions.append("losses_pct not provided; defaulted to 14.0% (PVWatts default)")

    dc_ac_ratio = spec.dc_ac_ratio
    if dc_ac_ratio is None:
        dc_ac_ratio = DEFAULT_DC_AC_RATIO
        assumptions.append("dc_ac_ratio not provided; defaulted to 1.2 (PVWatts default)")

    bifaciality: float | None = None
    if bifacial:
        bifaciality = DEFAULT_BIFACIALITY
        assumptions.append(
            f"bifacial=True; bifaciality coefficient assumed {DEFAULT_BIFACIALITY} "
            "(typical mid-range)"
        )
    if albedo is None:
        assumptions.append("albedo from weather file (not overridden)")

    assumptions.append("weather: NSRDB TMY (dataset=nsrdb), typical meteorological year")

    request = build_pvwatts_request(
        lat=spec.lat,
        lon=spec.lon,
        system_capacity=system_capacity_kw,
        tilt=tilt,
        azimuth=azimuth,
        array_type=array_type,
        module_type=module_type,
        losses=losses,
        dc_ac_ratio=dc_ac_ratio,
        bifaciality=bifaciality,
        albedo=albedo,
    )
    return ResolvedRequest(request=request, assumptions=assumptions, warnings=warnings)


async def estimate_production(
    client: SolarHttpClient,
    spec: SystemSpec,
    system_capacity_kw: float,
    *,
    bifacial: bool = False,
    albedo: float | None = None,
) -> ToolResult:
    resolved = resolve_request(spec, system_capacity_kw, bifacial=bifacial, albedo=albedo)
    result = await api.pvwatts(client, resolved.request)
    outputs = result.response.outputs

    warnings = [*resolved.warnings, *result.response.warnings, PVWATTS_CAVEAT]
    warnings.extend(freshness_warnings(result.fetched))
    station = result.response.station_info
    distance = station.distance if station is not None else None
    if distance is not None and distance > STATION_DISTANCE_WARN_METERS:
        warnings.append(
            f"Nearest NSRDB weather cell is {distance / 1000:.0f} km from "
            "the requested site; estimates may be less representative."
        )

    data: dict[str, Any] = {
        "ac_annual_kwh": outputs.ac_annual,
        "ac_monthly": outputs.ac_monthly,
        "capacity_factor": outputs.capacity_factor,
        "solrad_annual": outputs.solrad_annual,
    }
    return ToolResult(
        data=data,
        units={
            "ac_annual_kwh": units.KWH_AC_PER_YEAR,
            "ac_monthly": units.KWH_AC,
            "capacity_factor": units.PERCENT,
            "solrad_annual": units.KWH_PER_M2_DAY,
        },
        source=source_ref("NREL PVWatts v8", result.fetched, client.config.license_note),
        assumptions=resolved.assumptions,
        warnings=warnings,
    )
