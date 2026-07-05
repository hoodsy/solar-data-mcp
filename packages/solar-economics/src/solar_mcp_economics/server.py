"""FastMCP server exposing the solar-economics tools over stdio.

Same shape as nrel-solar: thin shims, logic in tools/, one client per source
shared for the server's lifetime plus one bulk store handle.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol, TypeVar

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from solar_mcp_core.bulk import BulkStore
from solar_mcp_core.config import EIA, NREL, OPENEI
from solar_mcp_core.envelope import ToolResult
from solar_mcp_core.http import SolarHttpClient, configure_debug_logging

from solar_mcp_economics import resources
from solar_mcp_economics.tools.estimate_roi import estimate_roi as _roi
from solar_mcp_economics.tools.get_electricity_prices import (
    get_electricity_prices as _prices,
)
from solar_mcp_economics.tools.incentive_tools import get_incentives as _incentives
from solar_mcp_economics.tools.incentive_tools import sync_incentives as _sync
from solar_mcp_economics.tools.lookup_tariffs import lookup_tariffs as _tariffs


@dataclass
class AppContext:
    openei: SolarHttpClient
    eia: SolarHttpClient
    nrel: SolarHttpClient
    store: BulkStore

    async def aclose(self) -> None:
        await self.openei.aclose()
        await self.eia.aclose()
        await self.nrel.aclose()
        self.store.close()


class EconomicsDeps(Protocol):
    """Context fields the economics tools read. Any hosting server's lifespan
    context must provide these — this package's AppContext does, and so does
    the solar-data-mcp umbrella's composite context."""

    openei: SolarHttpClient
    eia: SolarHttpClient
    nrel: SolarHttpClient
    store: BulkStore


DepsT = TypeVar("DepsT", bound=EconomicsDeps)

ToolContext = Context[ServerSession, EconomicsDeps]


def default_context() -> AppContext:
    return AppContext(
        openei=SolarHttpClient(OPENEI),
        eia=SolarHttpClient(EIA),
        nrel=SolarHttpClient(NREL),
        store=BulkStore(),
    )


def register_tools(mcp: FastMCP[DepsT]) -> None:
    @mcp.tool()
    async def lookup_tariffs(
        ctx: ToolContext,
        lat: float | None = None,
        lon: float | None = None,
        utility_name: str | None = None,
        sector: str | None = None,
    ) -> ToolResult:
        """Find retail electric rate schedules serving a point or a utility (URDB).

        Use this to answer "what does electricity cost on my bill here". Use
        get_electricity_prices for state-level averages and trends instead of
        actual filed tariffs. Provide either lat+lon or utility_name (not both);
        sector defaults to residential (stated in assumptions).

        Example: lookup_tariffs(lat=39.74, lon=-105.18) -> Xcel (PSCo) residential
        schedules with $/kWh tiers.

        Units: energy tier rates in USD/kWh; fixed charges in USD/month.
        Time-of-use schedules are flagged (is_tou) — tier values shown are an
        approximation for those.
        """
        return await _tariffs(
            ctx.request_context.lifespan_context.openei,
            lat=lat,
            lon=lon,
            utility_name=utility_name,
            sector=sector,
        )

    @mcp.tool()
    async def get_electricity_prices(
        ctx: ToolContext,
        state: str,
        sector: str | None = None,
        months: int | None = None,
    ) -> ToolResult:
        """State average retail electricity price with a monthly trend (EIA v2).

        Use this for "what do people pay in Colorado" or rate-escalation context.
        Use lookup_tariffs for the actual rate schedules a specific address sees.
        sector defaults to residential; months defaults to a 12-month trend.

        Example: get_electricity_prices(state="CO") -> latest and average
        cents/kWh plus the last 12 monthly points.

        Units: prices in cents/kWh; periods are YYYY-MM.
        """
        return await _prices(
            ctx.request_context.lifespan_context.eia, state=state, sector=sector, months=months
        )

    @mcp.tool()
    async def get_incentives(
        ctx: ToolContext, state: str, install_year: int | None = None
    ) -> ToolResult:
        """Solar incentives: federal ITC (current law, cited) + state/local programs.

        Use this to enumerate what reduces system cost. The federal table is
        always available; state/local programs come from a locally synced DSIRE
        snapshot (run sync_incentives first — a warning tells you if it's missing).

        Example: get_incentives(state="CO") -> 30% federal ITC + Colorado programs.

        Units: none (program terms are text); snapshot vintage is an ISO date.
        """
        return await _incentives(
            ctx.request_context.lifespan_context.store, state=state, install_year=install_year
        )

    @mcp.tool()
    async def sync_incentives(
        ctx: ToolContext, source: str, vintage: str | None = None
    ) -> ToolResult:
        """Load a DSIRE program export (CSV path or https URL) into the local store.

        Use this once (and after DSIRE refreshes) so get_incentives can return
        state/local programs. This WRITES to the local bulk store — the only
        state this server keeps. vintage defaults to today's date.

        Example: sync_incentives(source="/downloads/dsire-programs.csv",
        vintage="2026-06") -> rows_loaded.

        Units: rows_loaded is a count; vintage is an ISO date.
        """
        return await _sync(
            ctx.request_context.lifespan_context.store, source=source, vintage=vintage
        )

    @mcp.tool()
    async def estimate_roi(
        ctx: ToolContext,
        lat: float,
        lon: float,
        system_capacity_kw: float,
        state: str | None = None,
        install_cost_usd: float | None = None,
        cost_per_watt: float | None = None,
        annual_consumption_kwh: float | None = None,
        escalation_pct: float | None = None,
        discount_rate_pct: float | None = None,
        install_year: int | None = None,
    ) -> ToolResult:
        """Screening ROI for a solar system: payback, NPV, IRR, 25-yr cash flow.

        Use this for "would solar pay off here". It chains PVWatts production,
        URDB tariffs (EIA state average as fallback — pass state=XX to enable),
        and the federal ITC into one auditable calculation; audit_trail lists
        every component's source. It is explicitly NOT a quote (see warnings).
        Defaults (each stated in assumptions): escalation 2.5%/yr, discount 6%,
        install year = current year; cost falls back to the Tracking the Sun
        state median (needs state=XX and a synced snapshot) or a cited national
        median.

        Example: estimate_roi(lat=39.74, lon=-105.18, system_capacity_kw=6,
        state="CO") -> payback_years ~9, npv_usd, irr_pct, cash_flow table.

        Units: money in USD; rates in USD/kWh; payback in years; IRR in percent.
        """
        context = ctx.request_context.lifespan_context
        return await _roi(
            context.nrel,
            context.openei,
            context.eia,
            context.store,
            lat=lat,
            lon=lon,
            system_capacity_kw=system_capacity_kw,
            state=state,
            install_cost_usd=install_cost_usd,
            cost_per_watt=cost_per_watt,
            annual_consumption_kwh=annual_consumption_kwh,
            escalation_pct=escalation_pct,
            discount_rate_pct=discount_rate_pct,
            install_year=install_year,
        )


def create_server(context_factory: Callable[[], AppContext] | None = None) -> FastMCP:
    factory = context_factory if context_factory is not None else default_context

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
        context = factory()
        try:
            yield context
        finally:
            await context.aclose()

    mcp: FastMCP[AppContext] = FastMCP(
        "solar-economics",
        instructions=(
            "Solar economics from open US data: retail tariffs (URDB), electricity "
            "prices (EIA), incentives (federal ITC + DSIRE), and the auditable "
            "estimate_roi composite. Every tool returns data + units + source + "
            "assumptions + warnings; read the assumptions before quoting numbers."
        ),
        lifespan=lifespan,
    )
    register_tools(mcp)
    resources.register(mcp)
    return mcp


def main() -> None:
    configure_debug_logging()
    create_server().run()


if __name__ == "__main__":
    main()
