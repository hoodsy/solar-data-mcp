"""FastMCP server exposing the four nrel-solar tools over stdio.

Shims here are deliberately thin: all logic lives in plain typed functions
under tools/ (they get direct tests; the FastMCP decorator erases signatures
for mypy). One SolarHttpClient is shared for the server's lifetime via the
lifespan context, so the cache and rate limiter are shared across tools.

System parameters default to None rather than concrete values: a None means
"let the tool choose the documented default and say so in assumptions" —
explicitly-passed values are never reported as assumptions.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from solar_mcp_core.config import NREL
from solar_mcp_core.envelope import ToolResult
from solar_mcp_core.http import SolarHttpClient, configure_debug_logging

from solar_mcp_nrel import resources
from solar_mcp_nrel.models import SystemSpec
from solar_mcp_nrel.tools.compare_orientations import compare_orientations as _compare
from solar_mcp_nrel.tools.estimate_production import estimate_production as _estimate
from solar_mcp_nrel.tools.get_solar_resource import get_solar_resource as _resource
from solar_mcp_nrel.tools.size_system_for_target import size_system_for_target as _size


@dataclass
class AppContext:
    client: SolarHttpClient

    async def aclose(self) -> None:
        await self.client.aclose()


ToolContext = Context[ServerSession, AppContext]


def default_context() -> AppContext:
    return AppContext(client=SolarHttpClient(NREL))


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
        "nrel-solar",
        instructions=(
            "US solar data from NREL: PVWatts v8 production modeling and NSRDB "
            "irradiance. Every tool returns data + units + source + assumptions "
            "+ warnings; read the assumptions before quoting numbers."
        ),
        lifespan=lifespan,
    )

    @mcp.tool()
    async def estimate_production(
        lat: float,
        lon: float,
        system_capacity_kw: float,
        ctx: ToolContext,
        tilt_deg: float | None = None,
        azimuth_deg: float | None = None,
        array_type: str | None = None,
        module_type: str | None = None,
        losses_pct: float | None = None,
        bifacial: bool = False,
        albedo: float | None = None,
        dc_ac_ratio: float | None = None,
    ) -> ToolResult:
        """Estimate annual and monthly AC production for a PV system (PVWatts v8).

        Use this when the user describes a specific system at a location. Use
        get_solar_resource for raw irradiance without a system, compare_orientations
        to sweep tilt/azimuth options, size_system_for_target to go from a kWh
        goal to a system size.

        Unset parameters default to: tilt = site latitude, azimuth 180 (south),
        array_type fixed_roof, module_type standard, losses 14%, dc_ac_ratio 1.2
        — each applied default is listed in the result's assumptions.

        Example: estimate_production(lat=33.42, lon=-111.83, system_capacity_kw=8,
        tilt_deg=25) -> ~14,100 kWh/yr for Mesa, AZ.

        Units: ac_annual_kwh in kWh AC/year; ac_monthly in kWh AC per month;
        capacity_factor in percent; solrad_annual in kWh/m2/day. tilt_deg and
        azimuth_deg in degrees (azimuth 180 = south); losses_pct in percent.
        """
        spec = SystemSpec(
            lat=lat,
            lon=lon,
            tilt_deg=tilt_deg,
            azimuth_deg=azimuth_deg,
            array_type=array_type,
            module_type=module_type,
            losses_pct=losses_pct,
            dc_ac_ratio=dc_ac_ratio,
        )
        return await _estimate(
            ctx.request_context.lifespan_context.client,
            spec,
            system_capacity_kw,
            bifacial=bifacial,
            albedo=albedo,
        )

    @mcp.tool()
    async def get_solar_resource(lat: float, lon: float, ctx: ToolContext) -> ToolResult:
        """Get annual/monthly solar irradiance (GHI, DNI) for a location (NSRDB).

        Use this for "how sunny is it there" questions with no specific system.
        Use estimate_production when a system size is known — it already folds
        irradiance in.

        Example: get_solar_resource(lat=39.74, lon=-105.18) -> ghi_annual ~4.8.

        Units: ghi_*/dni_* in kWh/m2/day; resolved_cell_lat/lon in degrees
        (center of the 0.1-degree NSRDB cell actually answering the query).
        """
        return await _resource(ctx.request_context.lifespan_context.client, lat=lat, lon=lon)

    @mcp.tool()
    async def compare_orientations(
        lat: float,
        lon: float,
        system_capacity_kw: float,
        ctx: ToolContext,
        tilts: list[float] | None = None,
        azimuths: list[float] | None = None,
        array_type: str | None = None,
        module_type: str | None = None,
        losses_pct: float | None = None,
        dc_ac_ratio: float | None = None,
    ) -> ToolResult:
        """Rank tilt x azimuth combinations by annual production for one system.

        Use this for "how bad is my north-facing roof really" or "is 10 vs 25
        degrees of tilt worth it". Use estimate_production for a single known
        orientation. The sweep is capped at 25 combinations per call; unset
        tilts/azimuths sweep a default 5x5 grid.

        Example: compare_orientations(lat=33.42, lon=-111.83,
        system_capacity_kw=8, tilts=[10, 25], azimuths=[180]) -> ranked table
        with pct_delta_vs_best.

        Units: tilt_deg/azimuth_deg in degrees (azimuth 90=E, 180=S, 270=W);
        ac_annual_kwh in kWh AC/year; pct_delta_vs_best in percent (0 = best).
        """
        spec = SystemSpec(
            lat=lat,
            lon=lon,
            array_type=array_type,
            module_type=module_type,
            losses_pct=losses_pct,
            dc_ac_ratio=dc_ac_ratio,
        )
        return await _compare(
            ctx.request_context.lifespan_context.client,
            spec,
            system_capacity_kw,
            tilts=tilts,
            azimuths=azimuths,
        )

    @mcp.tool()
    async def size_system_for_target(
        lat: float,
        lon: float,
        target_annual_kwh: float,
        ctx: ToolContext,
        tilt_deg: float | None = None,
        azimuth_deg: float | None = None,
        array_type: str | None = None,
        module_type: str | None = None,
        losses_pct: float | None = None,
        dc_ac_ratio: float | None = None,
    ) -> ToolResult:
        """Find the system size (kW) that produces a target annual kWh.

        Use this to size a system from a consumption goal ("my home uses 9,000
        kWh/yr"). Use estimate_production when the size is already known.
        Solves to within 2% using at most 6 PVWatts calls. Unset parameters
        default as in estimate_production (each default listed in assumptions).

        Example: size_system_for_target(lat=39.74, lon=-105.18,
        target_annual_kwh=6000, tilt_deg=25) -> required_kw ~3.6.

        Units: required_kw in kW DC; achieved_annual_kwh in kWh AC/year;
        pct_error in percent (achieved vs target).
        """
        spec = SystemSpec(
            lat=lat,
            lon=lon,
            tilt_deg=tilt_deg,
            azimuth_deg=azimuth_deg,
            array_type=array_type,
            module_type=module_type,
            losses_pct=losses_pct,
            dc_ac_ratio=dc_ac_ratio,
        )
        return await _size(ctx.request_context.lifespan_context.client, spec, target_annual_kwh)

    resources.register(mcp)
    return mcp


def main() -> None:
    configure_debug_logging()
    create_server().run()


if __name__ == "__main__":
    main()
