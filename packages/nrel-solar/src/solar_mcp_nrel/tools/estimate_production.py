"""estimate_production: annual/monthly AC output for a PV system via PVWatts v8."""

from dataclasses import dataclass
from typing import Any

from solar_mcp_core import units
from solar_mcp_core.envelope import ToolResult
from solar_mcp_core.http import SolarHttpClient

from solar_mcp_nrel import api
from solar_mcp_nrel.models import PVWattsRequest, build_pvwatts_request
from solar_mcp_nrel.tools._envelope import PVWATTS_CAVEAT, freshness_warnings, source_ref

DEFAULT_BIFACIALITY = 0.7  # typical mid-range for bifacial modules per PVWatts docs
STATION_DISTANCE_WARN_METERS = 32_000


@dataclass
class ResolvedRequest:
    request: PVWattsRequest
    assumptions: list[str]
    warnings: list[str]


def resolve_request(
    *,
    lat: float,
    lon: float,
    system_capacity_kw: float,
    tilt_deg: float | None,
    azimuth_deg: float,
    array_type: str,
    module_type: str,
    losses_pct: float,
    bifacial: bool,
    albedo: float | None,
    dc_ac_ratio: float,
) -> ResolvedRequest:
    """Apply spec'd defaults, recording every injected value as an assumption.

    Pure function — all defaulting logic is unit-testable without HTTP.
    """
    assumptions: list[str] = []
    warnings: list[str] = []

    if tilt_deg is None:
        tilt_deg = min(abs(lat), 90.0)
        assumptions.append(
            f"tilt_deg not provided; defaulted to site latitude ({tilt_deg:.1f} deg)"
        )
    if azimuth_deg == 180.0:
        assumptions.append("azimuth_deg=180 (south-facing)")
        if lat < 0:
            warnings.append(
                "Southern-hemisphere site with south-facing azimuth: north-facing "
                "(azimuth_deg=0) is usually optimal below the equator."
            )
    if array_type == "fixed_roof":
        assumptions.append("array_type=fixed_roof (fixed array, roof mounted)")
    if module_type == "standard":
        assumptions.append("module_type=standard (crystalline silicon, ~19% efficiency)")
    if losses_pct == 14.0:
        assumptions.append("losses_pct=14.0 (PVWatts default system losses)")
    if dc_ac_ratio == 1.2:
        assumptions.append("dc_ac_ratio=1.2 (PVWatts default)")

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
        lat=lat,
        lon=lon,
        system_capacity=system_capacity_kw,
        tilt=tilt_deg,
        azimuth=azimuth_deg,
        array_type=array_type,
        module_type=module_type,
        losses=losses_pct,
        dc_ac_ratio=dc_ac_ratio,
        bifaciality=bifaciality,
        albedo=albedo,
    )
    return ResolvedRequest(request=request, assumptions=assumptions, warnings=warnings)


async def estimate_production(
    client: SolarHttpClient,
    *,
    lat: float,
    lon: float,
    system_capacity_kw: float,
    tilt_deg: float | None = None,
    azimuth_deg: float = 180.0,
    array_type: str = "fixed_roof",
    module_type: str = "standard",
    losses_pct: float = 14.0,
    bifacial: bool = False,
    albedo: float | None = None,
    dc_ac_ratio: float = 1.2,
) -> ToolResult:
    resolved = resolve_request(
        lat=lat,
        lon=lon,
        system_capacity_kw=system_capacity_kw,
        tilt_deg=tilt_deg,
        azimuth_deg=azimuth_deg,
        array_type=array_type,
        module_type=module_type,
        losses_pct=losses_pct,
        bifacial=bifacial,
        albedo=albedo,
        dc_ac_ratio=dc_ac_ratio,
    )
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
        source=source_ref("NREL PVWatts v8", result.fetched),
        assumptions=resolved.assumptions,
        warnings=warnings,
    )
