"""Server-level tests over an in-memory MCP session (no subprocess, no network)."""

from collections.abc import AsyncIterator, Callable

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent
from solar_mcp_core.config import NREL, SourceConfig
from solar_mcp_core.errors import SolarMCPError
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_forecast.predictor import (
    INSTALL_HINT,
    ForecastPoint,
    ForecastRequest,
    quartz_predictor,
)
from solar_mcp_forecast.server import AppContext, create_server

from conftest import assert_tool_docs

ClientFor = Callable[[SourceConfig], SolarHttpClient]

EXPECTED_TOOLS = {"forecast_generation", "compare_forecast_to_model"}


def stub_predictor(request: ForecastRequest) -> list[ForecastPoint]:
    return [
        ForecastPoint(time=f"2026-07-05T{hour:02d}:00:00Z", power_kw=1.0)
        for hour in range(request.horizon_hours)
    ]


@pytest.fixture
async def session(client_for: ClientFor) -> AsyncIterator[object]:
    def context() -> AppContext:
        return AppContext(predictor=stub_predictor, nrel=client_for(NREL))

    server = create_server(context_factory=context)
    async with create_connected_server_and_client_session(
        server._mcp_server, raise_exceptions=True
    ) as client_session:
        yield client_session


@pytest.mark.anyio
async def test_lists_both_tools_with_docs(session) -> None:  # type: ignore[no-untyped-def]
    tools = await session.list_tools()
    assert {tool.name for tool in tools.tools} == EXPECTED_TOOLS
    assert_tool_docs(tools.tools)


@pytest.mark.anyio
async def test_forecast_over_mcp(session) -> None:  # type: ignore[no-untyped-def]
    result = await session.call_tool(
        "forecast_generation",
        {"lat": 39.74, "lon": -105.18, "capacity_kw": 6.0, "horizon_hours": 12},
    )
    assert not result.isError
    structured = result.structuredContent
    assert structured is not None
    for key in ("data", "units", "source", "assumptions", "warnings"):
        assert key in structured
    assert structured["data"]["total_kwh"] == pytest.approx(12.0)


@pytest.mark.anyio
async def test_bad_horizon_reported_not_crash(session) -> None:  # type: ignore[no-untyped-def]
    result = await session.call_tool(
        "forecast_generation",
        {"lat": 39.74, "lon": -105.18, "capacity_kw": 6.0, "horizon_hours": 99},
    )
    assert result.isError
    assert isinstance(result.content[0], TextContent)
    assert "horizon_hours" in result.content[0].text


@pytest.mark.anyio
async def test_resources_exposed(session) -> None:  # type: ignore[no-untyped-def]
    resources = await session.list_resources()
    uris = {str(resource.uri) for resource in resources.resources}
    assert {"source://quartz/license", "source://solar-forecast/coverage"} <= uris


def test_quartz_predictor_missing_is_actionable() -> None:
    """quartz-solar-forecast is not installed in this workspace (pydantic pin
    conflict) — the predictor must fail with install instructions, not a bare
    ImportError."""
    request = ForecastRequest(
        lat=39.74,
        lon=-105.18,
        capacity_kw=6.0,
        tilt_deg=25.0,
        azimuth_deg=180.0,
        horizon_hours=4,
    )
    with pytest.raises(SolarMCPError) as excinfo:
        quartz_predictor(request)
    assert str(excinfo.value) == INSTALL_HINT
