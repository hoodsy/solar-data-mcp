"""FastMCP server exposing the solar-market tools over stdio.

Same shape as the other servers: thin shims, logic in tools/, one client per
REST source plus the shared bulk store. The two sync_* tools are the only
writers (local DuckDB only) — everything else is read-only.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol, TypeVar

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from solar_mcp_core.bulk import BulkStore
from solar_mcp_core.config import AHJ, USPVDB
from solar_mcp_core.envelope import ToolResult
from solar_mcp_core.http import SolarHttpClient, configure_debug_logging

from solar_mcp_market import resources
from solar_mcp_market.tools.find_utility_scale_projects import (
    find_utility_scale_projects as _projects,
)
from solar_mcp_market.tools.get_permitting_timelines import (
    get_permitting_timelines as _timelines,
)
from solar_mcp_market.tools.identify_ahj import identify_ahj as _ahj
from solar_mcp_market.tools.market_snapshot import market_snapshot as _snapshot
from solar_mcp_market.tools.query_installed_systems import (
    query_installed_systems as _installs,
)
from solar_mcp_market.tools.sync_tools import sync_solartrace as _sync_st
from solar_mcp_market.tools.sync_tools import sync_tracking_the_sun as _sync_tts


@dataclass
class AppContext:
    uspvdb: SolarHttpClient
    ahj: SolarHttpClient
    store: BulkStore

    async def aclose(self) -> None:
        await self.uspvdb.aclose()
        await self.ahj.aclose()
        self.store.close()


class MarketDeps(Protocol):
    """Context fields the market tools read. Any hosting server's lifespan
    context must provide these — this package's AppContext does, and so does
    the solar-data-mcp umbrella's composite context."""

    uspvdb: SolarHttpClient
    ahj: SolarHttpClient
    store: BulkStore


DepsT = TypeVar("DepsT", bound=MarketDeps)

ToolContext = Context[ServerSession, MarketDeps]


def default_context() -> AppContext:
    return AppContext(uspvdb=SolarHttpClient(USPVDB), ahj=SolarHttpClient(AHJ), store=BulkStore())


def register_tools(mcp: FastMCP[DepsT]) -> None:
    @mcp.tool()
    async def sync_tracking_the_sun(
        ctx: ToolContext,
        source: str,
        vintage: str | None = None,
        state: str | None = None,
    ) -> ToolResult:
        """Load an LBNL Tracking the Sun release into the local bulk store.

        Use this once per release (files are ~1-2 GB; they stream, never held
        in memory; pass state=XX to keep only one state). This WRITES to the
        local store. Download releases from https://emp.lbl.gov/tracking-the-sun.

        Example: sync_tracking_the_sun(source="/downloads/tts_2024.csv",
        vintage="2024", state="CO") -> rows_loaded.

        Units: rows_loaded is a count; vintage is a date/label.
        """
        return await _sync_tts(
            ctx.request_context.lifespan_context.store,
            source=source,
            vintage=vintage,
            state=state,
        )

    @mcp.tool()
    async def sync_solartrace(
        ctx: ToolContext, source: str, vintage: str | None = None
    ) -> ToolResult:
        """Load a SolarTRACE dataset export into the local bulk store.

        Use this before get_permitting_timelines. This WRITES to the local
        store. Download the dataset from https://maps.nlr.gov/solarTRACE/.

        Example: sync_solartrace(source="/downloads/solartrace.csv",
        vintage="2025-H2") -> rows_loaded.

        Units: rows_loaded is a count; vintage is a date/label.
        """
        return await _sync_st(
            ctx.request_context.lifespan_context.store, source=source, vintage=vintage
        )

    @mcp.tool()
    async def query_installed_systems(
        ctx: ToolContext,
        state: str,
        year_start: int | None = None,
        year_end: int | None = None,
    ) -> ToolResult:
        """Aggregate stats from installed-system records: median $/W, sizes, equipment.

        Use this for "what do systems cost/look like in state X". Returns
        aggregates only, never row-level records. Needs a synced Tracking the
        Sun snapshot (the error tells you if it's missing).

        Example: query_installed_systems(state="CO", year_start=2022) ->
        median_price_per_watt ~3.2, size quartiles, top module makers.

        Units: prices in USD/W; sizes in kW DC; counts are counts.
        """
        return await _installs(
            ctx.request_context.lifespan_context.store,
            state=state,
            year_start=year_start,
            year_end=year_end,
        )

    @mcp.tool()
    async def get_permitting_timelines(
        ctx: ToolContext, state: str | None = None, jurisdiction: str | None = None
    ) -> ToolResult:
        """Median permit, inspection, and interconnection (PTO) days (SolarTRACE).

        Use this for "how long does solar permitting take in X". Pass exactly
        one of state (all jurisdictions there) or jurisdiction (name match).
        Needs a synced SolarTRACE snapshot.

        Example: get_permitting_timelines(state="CO") -> per-jurisdiction rows
        plus statewide medians.

        Units: all durations in days.
        """
        return await _timelines(
            ctx.request_context.lifespan_context.store, state=state, jurisdiction=jurisdiction
        )

    @mcp.tool()
    async def find_utility_scale_projects(
        ctx: ToolContext,
        state: str | None = None,
        bbox: list[float] | None = None,
        min_capacity_mw: float | None = None,
        limit: int | None = None,
    ) -> ToolResult:
        """Ground-mounted utility-scale PV facilities (USPVDB, EIA-860 attributes).

        Use this for the large-plant landscape: "biggest solar farms in CO",
        "capacity near this area". Pass exactly one of state or
        bbox=[west, south, east, north]. Largest first; limit defaults to 25.

        Example: find_utility_scale_projects(state="CO", min_capacity_mw=100)
        -> projects with capacity_mw_ac, year, tracking type, battery flag.

        Units: capacities in MW AC/DC; coordinates in degrees.
        """
        return await _projects(
            ctx.request_context.lifespan_context.uspvdb,
            state=state,
            bbox=bbox,
            min_capacity_mw=min_capacity_mw,
            limit=limit,
        )

    @mcp.tool()
    async def identify_ahj(ctx: ToolContext, lat: float, lon: float) -> ToolResult:
        """Authority Having Jurisdiction + adopted codes for a point (SunSpec).

        Use this for "who permits solar at this location and under which code
        editions". Requires AHJ_REGISTRY_TOKEN (issued by support@sunspec.org);
        without it the error contains setup instructions. The registry request
        shape is unverified against the live service — treat results as leads,
        not filings-grade facts.

        Example: identify_ahj(lat=39.74, lon=-105.18) -> AHJ name, level,
        building/electric/fire code editions.

        Units: none (names and code editions are text).
        """
        return await _ahj(ctx.request_context.lifespan_context.ahj, lat=lat, lon=lon)

    @mcp.tool()
    async def market_snapshot(ctx: ToolContext, state: str) -> ToolResult:
        """One-call state market overview: installs, $/W, permitting, big projects.

        Use this to orient in a state before drilling into the specific tools.
        Best-effort composite: sections needing an unsynced snapshot are
        skipped with a warning instead of failing the whole call.

        Example: market_snapshot(state="CO") -> installed_systems stats,
        permitting medians, top-5 utility-scale projects, audit_trail.

        Units: per section — USD/W, days, MW AC; see nested unit entries.
        """
        context = ctx.request_context.lifespan_context
        return await _snapshot(context.uspvdb, context.store, state=state)


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
        "solar-market",
        instructions=(
            "US solar market intelligence: permitting timelines (SolarTRACE), "
            "installed-system stats (Tracking the Sun), utility-scale plants "
            "(USPVDB), AHJ lookup. Bulk datasets are local snapshots loaded by the "
            "sync_* tools; every result cites its snapshot vintage."
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
