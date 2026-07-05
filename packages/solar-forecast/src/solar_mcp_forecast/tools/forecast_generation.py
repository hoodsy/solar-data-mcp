"""forecast_generation: next-hours generation forecast from the open Quartz model."""

import asyncio
from datetime import UTC, datetime

from solar_mcp_core import units
from solar_mcp_core.envelope import SourceRef, ToolResult
from solar_mcp_core.errors import BadInput

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
) -> tuple[ForecastRequest, list[str]]:
    """Validate and default-fill, recording every injected default. Pure."""
    assumptions: list[str] = []
    if not -90 <= lat <= 90:
        raise BadInput(field="lat", value=lat, allowed="-90 to 90")
    if not -180 <= lon <= 180:
        raise BadInput(field="lon", value=lon, allowed="-180 to 180")
    if not 0.05 <= capacity_kw <= 500_000:
        raise BadInput(field="capacity_kw", value=capacity_kw, allowed="0.05 to 500000 kW")
    if tilt_deg is None:
        tilt_deg = min(abs(lat), 90.0)
        assumptions.append(
            f"tilt_deg not provided; defaulted to site latitude ({tilt_deg:.1f} deg)"
        )
    if not 0 <= tilt_deg <= 90:
        raise BadInput(field="tilt_deg", value=tilt_deg, allowed="0 to 90")
    if azimuth_deg is None:
        azimuth_deg = 180.0
        assumptions.append("azimuth_deg not provided; defaulted to 180 (south-facing)")
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
    return request, assumptions


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
    request, assumptions = resolve_forecast_request(
        lat=lat,
        lon=lon,
        capacity_kw=capacity_kw,
        tilt_deg=tilt_deg,
        azimuth_deg=azimuth_deg,
        horizon_hours=horizon_hours,
    )
    points = await asyncio.to_thread(predictor, request)  # model inference is CPU-bound

    total_kwh = round(sum(p.power_kw for p in points), 2)  # hourly points -> kW*1h
    peak = max(points, key=lambda p: p.power_kw) if points else None
    return ToolResult(
        data={
            "series": [{"time": p.time, "power_kw": round(p.power_kw, 3)} for p in points],
            "total_kwh": total_kwh,
            "peak_kw": round(peak.power_kw, 3) if peak else 0.0,
            "peak_time": peak.time if peak else None,
            "horizon_hours": request.horizon_hours,
        },
        units={
            "series[].time": units.ISO_DATE,
            "series[].power_kw": "kW_ac",
            "total_kwh": units.KWH,
            "peak_kw": "kW_ac",
            "peak_time": units.ISO_DATE,
            "horizon_hours": "hours",
        },
        source=SourceRef(
            name="Quartz Solar Forecast (Open Climate Fix)",
            url=QUARTZ_URL,
            retrieved_at=datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            license=QUARTZ_LICENSE,
        ),
        assumptions=[*assumptions, "cold-start forecast from NWP weather only (no live PV feed)"],
        warnings=[OPEN_MODEL_CAVEAT],
    )
