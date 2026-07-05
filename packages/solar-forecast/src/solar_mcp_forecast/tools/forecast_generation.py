"""forecast_generation: next-hours generation forecast from the open Quartz model."""

import asyncio

from solar_mcp_core import units
from solar_mcp_core.envelope import SourceRef, ToolResult, utc_now_iso
from solar_mcp_core.errors import BadInput, SolarMCPError, SourceUnavailable
from solar_mcp_core.validation import (
    default_tilt_azimuth,
    validate_capacity_kw,
    validate_lat_lon,
)

from solar_mcp_forecast.predictor import (
    QUARTZ_LICENSE,
    QUARTZ_URL,
    ForecastRequest,
    Predictor,
)

MAX_HORIZON_HOURS = 48
OPEN_MODEL_CAVEAT = (
    "Open-source ML forecast from public weather models (no live PV feed); "
    "useful for planning, not for grid settlement or contractual commitments."
)


def resolve_forecast_request(
    *,
    lat: float,
    lon: float,
    capacity_kw: float,
    tilt_deg: float | None,
    azimuth_deg: float | None,
    horizon_hours: int | None,
) -> tuple[ForecastRequest, list[str], list[str]]:
    """Validate and default-fill, recording every injected default. Pure."""
    validate_lat_lon(lat, lon)
    validate_capacity_kw(capacity_kw)
    tilt_deg, azimuth_deg, assumptions, warnings = default_tilt_azimuth(lat, tilt_deg, azimuth_deg)
    if not 0 <= tilt_deg <= 90:
        raise BadInput(field="tilt_deg", value=tilt_deg, allowed="0 to 90")
    if not 0 <= azimuth_deg < 360:
        raise BadInput(field="azimuth_deg", value=azimuth_deg, allowed="0 to <360")
    if horizon_hours is None:
        horizon_hours = MAX_HORIZON_HOURS
        assumptions.append(f"horizon_hours not provided; defaulted to {MAX_HORIZON_HOURS}")
    if not 1 <= horizon_hours <= MAX_HORIZON_HOURS:
        raise BadInput(
            field="horizon_hours", value=horizon_hours, allowed=f"1 to {MAX_HORIZON_HOURS}"
        )
    request = ForecastRequest(
        lat=lat,
        lon=lon,
        capacity_kw=capacity_kw,
        tilt_deg=tilt_deg,
        azimuth_deg=azimuth_deg,
        horizon_hours=horizon_hours,
    )
    return request, assumptions, warnings


async def forecast_generation(
    predictor: Predictor,
    *,
    lat: float,
    lon: float,
    capacity_kw: float,
    tilt_deg: float | None = None,
    azimuth_deg: float | None = None,
    horizon_hours: int | None = None,
) -> ToolResult:
    request, assumptions, site_warnings = resolve_forecast_request(
        lat=lat,
        lon=lon,
        capacity_kw=capacity_kw,
        tilt_deg=tilt_deg,
        azimuth_deg=azimuth_deg,
        horizon_hours=horizon_hours,
    )
    try:
        points = await asyncio.to_thread(predictor, request)  # model inference is CPU-bound
    except SolarMCPError:
        raise
    except Exception as exc:  # NWP download / schema errors from the model stack
        raise SourceUnavailable("quartz", f"{type(exc).__name__}: {exc}") from exc

    warnings = [*site_warnings, OPEN_MODEL_CAVEAT]
    if len(points) < request.horizon_hours:
        warnings.append(
            f"model returned {len(points)} of {request.horizon_hours} requested hours; "
            "totals cover the returned hours only"
        )

    total_kwh = round(sum(p.power_kw for p in points), 2)  # hourly points -> kW*1h
    peak = max(points, key=lambda p: p.power_kw) if points else None
    return ToolResult(
        data={
            "series": [{"time": p.time, "power_kw": round(p.power_kw, 3)} for p in points],
            "total_kwh": total_kwh,
            "peak_kw": round(peak.power_kw, 3) if peak else 0.0,
            "peak_time": peak.time if peak else None,
            "horizon_hours": request.horizon_hours,
            "hours_returned": len(points),
        },
        units={
            "series[].time": units.ISO_DATE,
            "series[].power_kw": units.KW_AC,
            "total_kwh": units.KWH,
            "peak_kw": units.KW_AC,
            "peak_time": units.ISO_DATE,
            "horizon_hours": units.HOURS,
            "hours_returned": units.HOURS,
        },
        source=SourceRef(
            name="Quartz Solar Forecast (Open Climate Fix)",
            url=QUARTZ_URL,
            retrieved_at=utc_now_iso(),
            license=QUARTZ_LICENSE,
        ),
        assumptions=[*assumptions, "cold-start forecast from NWP weather only (no live PV feed)"],
        warnings=warnings,
    )
