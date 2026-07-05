"""The predictor seam: everything model-specific behind one callable type.

Tools depend on `Predictor`, not on quartz — tests stub it, CI never loads the
ML stack, and the quartz import failure turns into an actionable message
instead of a broken server.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from solar_mcp_core.errors import SolarMCPError

QUARTZ_URL = "https://github.com/openclimatefix/quartz-solar-forecast"
QUARTZ_LICENSE = "MIT (Open Climate Fix); open NWP inputs, no API key"

INSTALL_HINT = (
    "quartz-solar-forecast is not installed. It pins pydantic==2.6.2 (conflicts "
    "with the MCP SDK) so it is not auto-installed; add it alongside with: "
    "pip install --no-deps quartz-solar-forecast && pip install "
    "pv-site-prediction xarray xgboost openmeteo-requests requests-cache "
    "retry-requests  (see the solar-data-mcp-forecast README)"
)


@dataclass(frozen=True)
class ForecastRequest:
    lat: float
    lon: float
    capacity_kw: float
    tilt_deg: float
    azimuth_deg: float
    horizon_hours: int


@dataclass(frozen=True)
class ForecastPoint:
    time: str  # ISO 8601 UTC, hourly steps
    power_kw: float


# Synchronous by design — model inference is CPU-bound; tools run it in a thread.
Predictor = Callable[[ForecastRequest], list[ForecastPoint]]


def quartz_predictor(request: ForecastRequest) -> list[ForecastPoint]:
    """Run the real Quartz model. Imported lazily; see INSTALL_HINT."""
    try:
        from quartz_solar_forecast.forecast import run_forecast
        from quartz_solar_forecast.pydantic_models import PVSite
    except ImportError as exc:
        raise SolarMCPError(INSTALL_HINT) from exc

    site = PVSite(
        latitude=request.lat,
        longitude=request.lon,
        capacity_kwp=request.capacity_kw,
        tilt=request.tilt_deg,
        orientation=request.azimuth_deg,
    )
    frame = run_forecast(site=site, ts=datetime.now(tz=UTC).replace(tzinfo=None))
    # Contract: hourly points. Quartz emits sub-hourly steps; resample to 1h means.
    hourly = frame.resample("1h").mean().head(request.horizon_hours)
    points: list[ForecastPoint] = []
    for timestamp, row in hourly.iterrows():
        points.append(
            ForecastPoint(
                time=timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                power_kw=float(row["power_kw"]),
            )
        )
    return points
