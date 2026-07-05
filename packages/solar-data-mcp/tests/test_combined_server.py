"""Umbrella-server tests: all four domains' tools on one FastMCP sharing one
composite context, over an in-memory MCP session (no subprocess, no network)."""

from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from solar_data_mcp.server import (
    CompositeContext,
    create_server,
    default_context,
    main,
    missing_key_note,
)
from solar_mcp_core.bulk import BulkStore
from solar_mcp_core.config import AHJ, EIA, NREL, OPENEI, USPVDB, SourceConfig
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_forecast.predictor import ForecastPoint, ForecastRequest

from conftest import assert_tool_docs

ClientFor = Callable[[SourceConfig], SolarHttpClient]

EXPECTED_TOOLS = {
    # nrel-solar
    "estimate_production",
    "get_solar_resource",
    "compare_orientations",
    "size_system_for_target",
    # solar-economics
    "lookup_tariffs",
    "get_electricity_prices",
    "get_incentives",
    "sync_incentives",
    "estimate_roi",
    # solar-market
    "sync_tracking_the_sun",
    "sync_solartrace",
    "query_installed_systems",
    "get_permitting_timelines",
    "find_utility_scale_projects",
    "identify_ahj",
    "market_snapshot",
    # solar-forecast
    "forecast_generation",
    "compare_forecast_to_model",
}

EXPECTED_RESOURCES = {
    "source://nrel/license",
    "source://nrel/coverage",
    "source://openei/license",
    "source://eia/license",
    "source://dsire/license",
    "source://solar-economics/coverage",
    "source://uspvdb/license",
    "source://tts/license",
    "source://solartrace/license",
    "source://ahj/license",
    "source://solar-market/coverage",
    "source://quartz/license",
    "source://solar-forecast/coverage",
}

# Same shape as the market tests' canonical export; kept inline because test
# modules must not import across packages. CO median price_per_watt = 3.25.
CANONICAL_TTS = (
    "state,year,price_per_watt,size_kw,module_manufacturer\n"
    "CO,2024,3.10,7.2,Qcells\n"
    "CO,2023,3.40,6.1,Qcells\n"
    "AZ,2024,2.60,8.0,First Solar\n"
)


def stub_predictor(request: ForecastRequest) -> list[ForecastPoint]:
    return [
        ForecastPoint(time=f"2026-07-05T{hour:02d}:00:00Z", power_kw=1.0)
        for hour in range(request.horizon_hours)
    ]


@pytest.fixture
async def session(client_for: ClientFor) -> AsyncIterator[object]:
    def context() -> CompositeContext:
        nrel = client_for(NREL)
        return CompositeContext(
            client=nrel,
            nrel=nrel,
            openei=client_for(OPENEI),
            eia=client_for(EIA),
            uspvdb=client_for(USPVDB),
            ahj=client_for(AHJ),
            store=BulkStore(path=":memory:"),
            predictor=stub_predictor,
        )

    server = create_server(context_factory=context)
    async with create_connected_server_and_client_session(
        server._mcp_server, raise_exceptions=True
    ) as client_session:
        yield client_session


@pytest.mark.anyio
async def test_lists_all_eighteen_tools_with_docs(session) -> None:  # type: ignore[no-untyped-def]
    tools = await session.list_tools()
    names = {tool.name for tool in tools.tools}
    assert names == EXPECTED_TOOLS
    assert_tool_docs(tools.tools)


@pytest.mark.anyio
async def test_all_thirteen_resources_exposed(session) -> None:  # type: ignore[no-untyped-def]
    resources = await session.list_resources()
    uris = {str(resource.uri) for resource in resources.resources}
    assert uris == EXPECTED_RESOURCES

    content = await session.read_resource("source://nrel/license")
    assert "developer.nlr.gov" in content.contents[0].text


@pytest.mark.anyio
async def test_nrel_tool_over_combined_server(session) -> None:  # type: ignore[no-untyped-def]
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


@pytest.mark.anyio
async def test_market_sync_feeds_economics_roi(session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """The combined server's point: market's sync and economics' ROI share ONE
    bulk store, so a snapshot loaded by one domain is visible to the other."""
    csv = tmp_path / "tts.csv"
    csv.write_text(CANONICAL_TTS)
    sync = await session.call_tool("sync_tracking_the_sun", {"source": str(csv), "vintage": "2024"})
    assert not sync.isError
    assert sync.structuredContent["data"]["rows_loaded"] == 3

    roi = await session.call_tool(
        "estimate_roi",
        {
            "lat": 39.74,
            "lon": -105.18,
            "system_capacity_kw": 4.0,
            "state": "CO",
            "install_year": 2026,
        },
    )
    assert not roi.isError
    structured = roi.structuredContent
    assert structured is not None
    assert structured["data"]["gross_cost_usd"] == pytest.approx(3.25 * 4000)
    assert any("Tracking the Sun snapshot" in a for a in structured["assumptions"])


@pytest.mark.anyio
async def test_forecast_tool_over_combined_server(session) -> None:  # type: ignore[no-untyped-def]
    result = await session.call_tool(
        "forecast_generation",
        {"lat": 39.74, "lon": -105.18, "capacity_kw": 6.0, "horizon_hours": 12},
    )
    assert not result.isError
    structured = result.structuredContent
    assert structured is not None
    assert structured["data"]["total_kwh"] == pytest.approx(12.0)


@pytest.mark.anyio
async def test_default_context_shares_nrel_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOLAR_DATA_MCP_CACHE_DIR", str(tmp_path))
    context = default_context()
    try:
        assert context.client is context.nrel, "NREL token bucket must be shared"
    finally:
        await context.aclose()


def test_missing_key_note_lists_unset_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for env in ("NREL_API_KEY", "OPENEI_API_KEY", "EIA_API_KEY", "AHJ_REGISTRY_TOKEN"):
        monkeypatch.delenv(env, raising=False)
    note = missing_key_note()
    assert note is not None
    for env in ("NREL_API_KEY", "OPENEI_API_KEY", "EIA_API_KEY", "AHJ_REGISTRY_TOKEN"):
        assert env in note
    assert "doctor" in note


def test_missing_key_note_silent_when_all_set(monkeypatch: pytest.MonkeyPatch) -> None:
    for env in ("NREL_API_KEY", "OPENEI_API_KEY", "EIA_API_KEY", "AHJ_REGISTRY_TOKEN"):
        monkeypatch.setenv(env, "TESTKEY")
    assert missing_key_note() is None


def test_main_doctor_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_cli(argv: list[str] | None = None) -> int:
        calls.append(list(argv or []))
        return 7

    monkeypatch.setattr("solar_data_mcp.server.core_cli_main", fake_cli)
    with pytest.raises(SystemExit) as excinfo:
        main(["doctor"])
    assert excinfo.value.code == 7
    assert calls == [["doctor"]]


def test_main_rejects_unknown_args(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["bogus"])
    assert excinfo.value.code == 2
    assert "usage" in capsys.readouterr().err
