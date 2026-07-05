"""Server-level tests over an in-memory MCP session (no subprocess, no network)."""

from collections.abc import AsyncIterator, Callable

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent
from solar_mcp_core.bulk import BulkStore
from solar_mcp_core.config import AHJ, USPVDB, SourceConfig
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_market.server import AppContext, create_server

ClientFor = Callable[[SourceConfig], SolarHttpClient]

EXPECTED_TOOLS = {
    "sync_tracking_the_sun",
    "sync_solartrace",
    "query_installed_systems",
    "get_permitting_timelines",
    "find_utility_scale_projects",
    "identify_ahj",
    "market_snapshot",
}


@pytest.fixture
async def session(client_for: ClientFor) -> AsyncIterator[object]:
    def context() -> AppContext:
        return AppContext(
            uspvdb=client_for(USPVDB), ahj=client_for(AHJ), store=BulkStore(path=":memory:")
        )

    server = create_server(context_factory=context)
    async with create_connected_server_and_client_session(
        server._mcp_server, raise_exceptions=True
    ) as client_session:
        yield client_session


@pytest.mark.anyio
async def test_lists_all_seven_tools_with_docs(session) -> None:  # type: ignore[no-untyped-def]
    tools = await session.list_tools()
    names = {tool.name for tool in tools.tools}
    assert names == EXPECTED_TOOLS
    for tool in tools.tools:
        assert tool.description, f"{tool.name} has no description"
        assert "Use this" in tool.description, f"{tool.name} lacks when-to-use guidance"
        assert "Example" in tool.description, f"{tool.name} lacks a worked example"
        assert "Units" in tool.description, f"{tool.name} lacks units documentation"


@pytest.mark.anyio
async def test_unsynced_query_reports_actionable_error(session) -> None:  # type: ignore[no-untyped-def]
    result = await session.call_tool("query_installed_systems", {"state": "CO"})
    assert result.isError
    assert isinstance(result.content[0], TextContent)
    assert "sync_tracking_the_sun" in result.content[0].text


@pytest.mark.anyio
async def test_resources_exposed(session) -> None:  # type: ignore[no-untyped-def]
    resources = await session.list_resources()
    uris = {str(resource.uri) for resource in resources.resources}
    assert {
        "source://uspvdb/license",
        "source://tts/license",
        "source://solartrace/license",
        "source://ahj/license",
        "source://solar-market/coverage",
    } <= uris
