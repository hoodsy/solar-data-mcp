"""FastMCP server exposing the solar-forecast tools over stdio.

The Quartz model is behind the Predictor seam: the server starts without it
installed, and forecast tools fail with install instructions rather than
breaking the whole server. compare_forecast_to_model additionally shares one
NREL client for the PVWatts TMY baseline.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from solar_mcp_core.config import NREL
from solar_mcp_core.envelope import ToolResult
from solar_mcp_core.http import SolarHttpClient, configure_debug_logging

from solar_mcp_forecast import resources
from solar_mcp_forecast.predictor import Predictor, quartz_predictor
from solar_mcp_forecast.tools.compare_forecast_to_model import (
    compare_forecast_to_model as _compare,
)
from solar_mcp_forecast.tools.forecast_generation import forecast_generation as _forecast


@dataclass
class AppContext:
    predictor: Predictor
    nrel: SolarHttpClient

    async def aclose(self) -> None:
        await self.nrel.aclose()


ToolContext = Context[ServerSession, AppContext]


def default_context() -> AppContext:
    return AppContext(predictor=quartz_predictor, nrel=SolarHttpClient(NREL))


def create_server(context_factory: Callable[[], AppContext] | None = None) -> FastMCP:
    factory = context_factory if context_factory is not None else default_context

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
        context = factory()
        try:
            yield context
        finally:
            await context.aclose()

    mcp = FastMCP(
        "solar-forecast",
        instructions=(
            "Solar generation forecasts from the open Quartz model (Open Climate "
            "Fix) — no API key. forecast_generation for the next <=48h; "
            "compare_forecast_to_model for 'is today unusual?' against PVWatts "
            "TMY. Screening-grade, not grid settlement."
        ),
        lifespan=lifespan,
    )

    @mcp.tool()
    async def forecast_generation(
        ctx: ToolContext,
        lat: float,
        lon: float,
        capacity_kw: float,
        tilt_deg: float | None = None,
        azimuth_deg: float | None = None,
        horizon_hours: int | None = None,
    ) -> ToolResult:
        """Hourly generation forecast for the next hours (Quartz open model).

        Use this for "how much will this system produce today/tomorrow".
        Use nrel-solar's estimate_production for typical-year expectations,
        and compare_forecast_to_model to judge whether the forecast is unusual.
        Defaults: tilt = site latitude, azimuth 180 (south), horizon 48h —
        each stated in assumptions. Max horizon 48 hours.

        Example: forecast_generation(lat=39.74, lon=-105.18, capacity_kw=6)
        -> hourly kW series, total_kwh, peak_kw.

        Units: power in kW AC; energy in kWh; times ISO 8601 UTC.
        """
        return await _forecast(
            ctx.request_context.lifespan_context.predictor,
            lat=lat,
            lon=lon,
            capacity_kw=capacity_kw,
            tilt_deg=tilt_deg,
            azimuth_deg=azimuth_deg,
            horizon_hours=horizon_hours,
        )

    @mcp.tool()
    async def compare_forecast_to_model(
        ctx: ToolContext,
        lat: float,
        lon: float,
        capacity_kw: float,
        tilt_deg: float | None = None,
        azimuth_deg: float | None = None,
        horizon_hours: int | None = None,
    ) -> ToolResult:
        """Is the forecast unusual? Quartz forecast vs PVWatts typical-year rate.

        Use this for "is today a good solar day here". Returns the forecast
        total, the TMY-typical total for the same horizon, their ratio, and a
        plain-language verdict. Horizons in multiples of 24h compare cleanest
        (see assumptions for the uniform-spread simplification).

        Example: compare_forecast_to_model(lat=39.74, lon=-105.18,
        capacity_kw=6, horizon_hours=24) -> ratio_pct ~120 on a clear day.

        Units: energies in kWh; ratio in percent.
        """
        context = ctx.request_context.lifespan_context
        return await _compare(
            context.predictor,
            context.nrel,
            lat=lat,
            lon=lon,
            capacity_kw=capacity_kw,
            tilt_deg=tilt_deg,
            azimuth_deg=azimuth_deg,
            horizon_hours=horizon_hours,
        )

    resources.register(mcp)
    return mcp


def main() -> None:
    configure_debug_logging()
    create_server().run()


if __name__ == "__main__":
    main()
