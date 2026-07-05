"""Server-level tests over an in-memory MCP session (no subprocess, no network)."""

from collections.abc import AsyncIterator, Callable

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from solar_mcp_core.bulk import BulkStore
from solar_mcp_core.config import EIA, NREL, OPENEI, SourceConfig
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_economics.server import AppContext, create_server

from conftest import assert_tool_docs

ClientFor = Callable[[SourceConfig], SolarHttpClient]

EXPECTED_TOOLS = {
    "lookup_tariffs",
    "get_electricity_prices",
    "get_incentives",
    "sync_incentives",
    "estimate_roi",
}


@pytest.fixture
async def session(client_for: ClientFor) -> AsyncIterator[object]:
    def context() -> AppContext:
        return AppContext(
            openei=client_for(OPENEI),
            eia=client_for(EIA),
            nrel=client_for(NREL),
            store=BulkStore(path=":memory:"),
        )

    server = create_server(context_factory=context)
    async with create_connected_server_and_client_session(
        server._mcp_server, raise_exceptions=True
    ) as client_session:
        yield client_session


@pytest.mark.anyio
async def test_lists_all_five_tools_with_docs(session) -> None:  # type: ignore[no-untyped-def]
    tools = await session.list_tools()
    names = {tool.name for tool in tools.tools}
    assert names == EXPECTED_TOOLS
    assert_tool_docs(tools.tools)


@pytest.mark.anyio
async def test_get_incentives_over_mcp(session) -> None:  # type: ignore[no-untyped-def]
    result = await session.call_tool("get_incentives", {"state": "CO", "install_year": 2026})
    assert not result.isError
    structured = result.structuredContent
    assert structured is not None
    for key in ("data", "units", "source", "assumptions", "warnings"):
        assert key in structured
    assert structured["data"]["federal"][0]["type"] == "tax credit"


@pytest.mark.anyio
async def test_resources_exposed(session) -> None:  # type: ignore[no-untyped-def]
    resources = await session.list_resources()
    uris = {str(resource.uri) for resource in resources.resources}
    assert {
        "source://openei/license",
        "source://eia/license",
        "source://dsire/license",
        "source://solar-economics/coverage",
    } <= uris
