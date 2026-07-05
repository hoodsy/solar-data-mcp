"""The umbrella server: all four domain servers' tools on one FastMCP over
stdio, so consumers install one `uvx solar-data-mcp` instead of four servers.

Each domain package exposes register_tools() typed against a Protocol of the
context fields its tools read; CompositeContext provides the union, and mypy
proves the wiring at every register call. The sharing is load-bearing, not
just convenient: one NREL client means one token bucket for the 1,000 req/hr
quota that nrel, economics, and forecast tools all draw from, and one
BulkStore handle sidesteps DuckDB's one-process-per-file lock that separate
economics and market processes fight over.
"""

import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP
from solar_mcp_core.bulk import BulkStore
from solar_mcp_core.cli import main as core_cli_main
from solar_mcp_core.config import AHJ, EIA, NREL, OPENEI, USPVDB, api_key_for
from solar_mcp_core.http import SolarHttpClient, configure_debug_logging
from solar_mcp_economics import resources as economics_resources
from solar_mcp_economics import server as economics_server
from solar_mcp_forecast import resources as forecast_resources
from solar_mcp_forecast import server as forecast_server
from solar_mcp_forecast.predictor import Predictor, quartz_predictor
from solar_mcp_market import resources as market_resources
from solar_mcp_market import server as market_server
from solar_mcp_nrel import resources as nrel_resources
from solar_mcp_nrel import server as nrel_server

from solar_data_mcp import skills

INSTRUCTIONS = (
    "All US open solar data in one server: NREL production modeling "
    "(estimate_production, get_solar_resource, compare_orientations, "
    "size_system_for_target), economics (lookup_tariffs, get_electricity_prices, "
    "get_incentives, sync_incentives, estimate_roi), market intelligence "
    "(query_installed_systems, get_permitting_timelines, "
    "find_utility_scale_projects, identify_ahj, market_snapshot, sync_* loaders), "
    "and forecasts (forecast_generation, compare_forecast_to_model). Every tool "
    "returns data + units + source + assumptions + warnings; read the "
    "assumptions before quoting numbers. Keys (env vars): NREL_API_KEY unlocks "
    "the production, ROI, and forecast-vs-model tools; OPENEI_API_KEY unlocks "
    "lookup_tariffs; EIA_API_KEY unlocks get_electricity_prices; "
    "AHJ_REGISTRY_TOKEN (optional) unlocks identify_ahj. Market and forecast "
    "tools need no key. Run `solar-data-mcp doctor` to check setup. "
    "Before any multi-tool workflow, read skill://solar/index and load the "
    "matching skill://solar/<name> resource — skills encode tool ordering, "
    "sync prerequisites, and reporting rules for common question shapes."
)


@dataclass
class CompositeContext:
    """The union of the four domain packages' Deps protocols.

    client and nrel are the SAME SolarHttpClient in default_context: nrel
    tools read .client while economics/forecast tools read .nrel, and all of
    them share one NREL token bucket only if the instance is shared.
    """

    client: SolarHttpClient
    nrel: SolarHttpClient
    openei: SolarHttpClient
    eia: SolarHttpClient
    uspvdb: SolarHttpClient
    ahj: SolarHttpClient
    store: BulkStore
    predictor: Predictor

    async def aclose(self) -> None:
        # Dedupe by identity: client is normally the same object as nrel.
        seen: set[int] = set()
        for client in (self.client, self.nrel, self.openei, self.eia, self.uspvdb, self.ahj):
            if id(client) not in seen:
                seen.add(id(client))
                await client.aclose()
        self.store.close()


def default_context() -> CompositeContext:
    nrel = SolarHttpClient(NREL)
    return CompositeContext(
        client=nrel,
        nrel=nrel,
        openei=SolarHttpClient(OPENEI),
        eia=SolarHttpClient(EIA),
        uspvdb=SolarHttpClient(USPVDB),
        ahj=SolarHttpClient(AHJ),
        store=BulkStore(),
        predictor=quartz_predictor,
    )


def create_server(context_factory: Callable[[], CompositeContext] | None = None) -> FastMCP:
    factory = context_factory if context_factory is not None else default_context

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[CompositeContext]:
        context = factory()
        try:
            yield context
        finally:
            await context.aclose()

    mcp: FastMCP[CompositeContext] = FastMCP(
        "solar-data",
        instructions=INSTRUCTIONS,
        lifespan=lifespan,
    )
    nrel_server.register_tools(mcp)
    economics_server.register_tools(mcp)
    market_server.register_tools(mcp)
    forecast_server.register_tools(mcp)
    for resources in (nrel_resources, economics_resources, market_resources, forecast_resources):
        resources.register(mcp)
    skills.register(mcp)
    return mcp


def missing_key_note() -> str | None:
    """One startup line naming unset keys, or None when everything is set.

    Startup must stay fast and offline, so this only reads the environment —
    `solar-data-mcp doctor` is the live check.
    """
    required = [config for config in (NREL, OPENEI, EIA) if api_key_for(config) is None]
    optional = [config for config in (AHJ,) if api_key_for(config) is None]
    if not required and not optional:
        return None
    parts = []
    if required:
        keys = ", ".join(f"{c.api_key_env} (get one: {c.signup_url})" for c in required)
        parts.append(f"missing keys: {keys}")
    if optional:
        keys = ", ".join(f"{c.api_key_env} ({c.signup_url})" for c in optional)
        parts.append(f"optional: {keys}")
    return (
        "solar-data-mcp: "
        + "; ".join(parts)
        + ". Tools needing a missing key return setup instructions; run "
        "`solar-data-mcp doctor` to verify your setup."
    )


def main(argv: list[str] | None = None) -> None:
    configure_debug_logging()
    args = sys.argv[1:] if argv is None else argv
    if args == ["doctor"]:
        raise SystemExit(core_cli_main(["doctor"]))
    if args:
        print("usage: solar-data-mcp [doctor]", file=sys.stderr)
        raise SystemExit(2)
    note = missing_key_note()
    if note is not None:
        print(note, file=sys.stderr)  # stderr: stdout belongs to the stdio transport
    create_server().run()


if __name__ == "__main__":
    main()
