"""Server-level tests over an in-memory MCP session (no subprocess, no network)."""

from collections.abc import AsyncIterator

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_nrel.server import create_server

from conftest import assert_tool_docs

EXPECTED_TOOLS = {
    "estimate_production",
    "get_solar_resource",
    "compare_orientations",
    "size_system_for_target",
}


@pytest.fixture
async def session(nrel_client: SolarHttpClient) -> AsyncIterator[object]:
    from solar_mcp_nrel.server import AppContext

    server = create_server(context_factory=lambda: AppContext(client=nrel_client))
    async with create_connected_server_and_client_session(
        server._mcp_server, raise_exceptions=True
    ) as client_session:
        yield client_session


@pytest.mark.anyio
async def test_lists_all_four_tools_with_docs(session) -> None:  # type: ignore[no-untyped-def]
    tools = await session.list_tools()
    names = {tool.name for tool in tools.tools}
    assert names == EXPECTED_TOOLS
    assert_tool_docs(tools.tools)


@pytest.mark.anyio
async def test_call_tool_returns_full_envelope(session) -> None:  # type: ignore[no-untyped-def]
    result = await session.call_tool(
        "estimate_production",
        {"lat": 39.74, "lon": -105.18, "system_capacity_kw": 4.0, "tilt_deg": 25.0},
    )
    assert not result.isError
    structured = result.structuredContent
    assert structured is not None
    for key in ("data", "units", "source", "assumptions", "warnings"):
        assert key in structured, f"envelope key {key} missing from structuredContent"
    assert structured["data"]["ac_annual_kwh"] > 0
    assert structured["source"]["name"] == "NREL PVWatts v8"
    assert structured["assumptions"], "assumptions must list injected defaults"


@pytest.mark.anyio
async def test_resources_exposed(session) -> None:  # type: ignore[no-untyped-def]
    resources = await session.list_resources()
    uris = {str(resource.uri) for resource in resources.resources}
    assert "source://nrel/license" in uris
    assert "source://nrel/coverage" in uris

    content = await session.read_resource("source://nrel/license")
    text = content.contents[0]
    assert "developer.nlr.gov" in text.text


@pytest.mark.anyio
async def test_tool_error_is_reported_not_crash(session) -> None:  # type: ignore[no-untyped-def]
    result = await session.call_tool(
        "estimate_production",
        {"lat": 39.74, "lon": -105.18, "system_capacity_kw": 4.0, "tilt_deg": 95.0},
    )
    assert result.isError
    assert isinstance(result.content[0], TextContent)
    message = result.content[0].text
    assert "tilt" in message and "0 to 90" in message
