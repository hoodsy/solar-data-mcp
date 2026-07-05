"""compare_forecast_to_model: is the next-hours forecast unusual vs TMY typical?"""

import calendar
from datetime import UTC, datetime

from solar_mcp_core import units
from solar_mcp_core.envelope import SourceRef, ToolResult
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_nrel.models import SystemSpec
from solar_mcp_nrel.tools.estimate_production import estimate_production

from solar_mcp_forecast.predictor import Predictor
from solar_mcp_forecast.tools.forecast_generation import forecast_generation

UNIFORM_ASSUMPTION = (
    "TMY expectation spreads the month's typical production uniformly across "
    "its hours; forecasts covering mostly daylight (or night) will skew high "
    "(or low) against it — horizons in multiples of 24h compare cleanest"
)


async def compare_forecast_to_model(
    predictor: Predictor,
    nrel_client: SolarHttpClient,
    *,
    lat: float,
    lon: float,
    capacity_kw: float,
    tilt_deg: float | None = None,
    azimuth_deg: float | None = None,
    horizon_hours: int | None = None,
) -> ToolResult:
    forecast = await forecast_generation(
        predictor,
        lat=lat,
        lon=lon,
        capacity_kw=capacity_kw,
        tilt_deg=tilt_deg,
        azimuth_deg=azimuth_deg,
        horizon_hours=horizon_hours,
    )
    horizon = int(forecast.data["horizon_hours"])
    forecast_kwh = float(forecast.data["total_kwh"])

    typical = await estimate_production(
        nrel_client,
        SystemSpec(lat=lat, lon=lon, tilt_deg=tilt_deg, azimuth_deg=azimuth_deg),
        capacity_kw,
    )
    now = datetime.now(tz=UTC)
    month_kwh = float(typical.data["ac_monthly"][now.month - 1])
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    expected_kwh = round(month_kwh / (days_in_month * 24) * horizon, 2)

    ratio_pct = round(forecast_kwh / expected_kwh * 100, 1) if expected_kwh > 0 else None
    if ratio_pct is None:
        verdict = "no typical-production baseline for this month"
    elif ratio_pct >= 115:
        verdict = f"unusually sunny: ~{ratio_pct - 100:.0f}% above a typical {now:%B}"
    elif ratio_pct <= 85:
        verdict = f"below typical: ~{100 - ratio_pct:.0f}% under a typical {now:%B}"
    else:
        verdict = f"close to typical for {now:%B}"

    warnings = [*forecast.warnings]
    if horizon % 24 != 0:
        warnings.append(
            f"horizon of {horizon}h is not a whole number of days; the daylight "
            "share skews the ratio (see assumptions)"
        )

    return ToolResult(
        data={
            "forecast_kwh": forecast_kwh,
            "tmy_expected_kwh": expected_kwh,
            "ratio_pct": ratio_pct,
            "verdict": verdict,
            "horizon_hours": horizon,
            "month": f"{now:%Y-%m}",
        },
        units={
            "forecast_kwh": units.KWH,
            "tmy_expected_kwh": units.KWH,
            "ratio_pct": units.PERCENT,
            "verdict": units.LABEL,
            "horizon_hours": "hours",
            "month": units.ISO_DATE,
        },
        source=SourceRef(
            name="Quartz forecast vs NREL PVWatts TMY (composite)",
            url="https://github.com/loganbernard/solar-data-mcp",
            retrieved_at=datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            license="Quartz: MIT (OCF); PVWatts: NREL Developer Network",
        ),
        assumptions=[*forecast.assumptions, UNIFORM_ASSUMPTION],
        warnings=warnings,
    )
