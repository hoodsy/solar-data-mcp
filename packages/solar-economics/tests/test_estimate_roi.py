from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from solar_mcp_core.bulk import BulkStore
from solar_mcp_core.cache import HttpCache
from solar_mcp_core.config import EIA, NREL, OPENEI, SourceConfig
from solar_mcp_core.errors import BadInput
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_core.ratelimit import TokenBucket
from solar_mcp_economics.tools.estimate_roi import estimate_roi

from conftest import FakeTime, RoutedTransport, assert_envelope

ClientFor = Callable[[SourceConfig], SolarHttpClient]


@pytest.mark.anyio
async def test_estimate_roi_replay_end_to_end(client_for: ClientFor) -> None:
    result = await estimate_roi(
        client_for(NREL),
        client_for(OPENEI),
        client_for(EIA),
        BulkStore(path=":memory:"),
        lat=39.74,
        lon=-105.18,
        system_capacity_kw=4.0,  # reuses the recorded Boulder production fixture
        state="CO",
        cost_per_watt=3.5,
        install_year=2026,
    )
    assert_envelope(result)
    data = result.data

    assert data["gross_cost_usd"] == pytest.approx(4.0 * 1000 * 3.5)
    assert data["itc_usd"] == pytest.approx(data["gross_cost_usd"] * 0.30)  # 2026 -> 30%
    assert data["net_cost_usd"] == pytest.approx(data["gross_cost_usd"] * 0.70)
    assert 0.01 < data["effective_rate_usd_per_kwh"] < 1.0
    assert len(data["cash_flow"]) == 25
    assert data["year1_savings_usd"] > 0
    if data["payback_years"] is not None:
        assert 0 < data["payback_years"] <= 25

    components = {entry["component"] for entry in data["audit_trail"]}
    assert components == {"production", "electricity_rate", "install_cost"}
    assert any("Screening estimate" in w for w in result.warnings)
    assert any("federal ITC 30%" in a for a in result.assumptions)
    assert any(a.startswith("production:") for a in result.assumptions)


@pytest.mark.anyio
async def test_roi_falls_back_to_eia_when_urdb_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for env in ("NREL_API_KEY", "OPENEI_API_KEY", "EIA_API_KEY"):
        monkeypatch.setenv(env, "TESTKEY")

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "api.openei.org":
            return httpx.Response(500)
        if host == "api.eia.gov":
            return httpx.Response(
                200,
                json={
                    "response": {
                        "total": "1",
                        "data": [
                            {
                                "period": "2026-04",
                                "stateid": "CO",
                                "sectorid": "RES",
                                "price": "15.00",
                            }
                        ],
                    }
                },
            )
        return httpx.Response(  # NREL PVWatts
            200,
            json={
                "errors": [],
                "warnings": [],
                "station_info": {"lat": 39.7, "lon": -105.2},
                "outputs": {
                    "ac_annual": 6000.0,
                    "ac_monthly": [500.0] * 12,
                    "solrad_annual": 4.8,
                    "capacity_factor": 17.0,
                },
            },
        )

    fake = FakeTime()
    transport = RoutedTransport(handler)

    def client(config: SourceConfig) -> SolarHttpClient:
        return SolarHttpClient(
            config,
            transport=transport,
            cache=HttpCache(path=tmp_path / f"{config.name}.db", clock=fake.clock),
            bucket=TokenBucket.per_hour(1000, clock=fake.clock, sleep=fake.sleep),
            sleep=fake.sleep,
        )

    result = await estimate_roi(
        client(NREL),
        client(OPENEI),
        client(EIA),
        BulkStore(path=":memory:"),
        lat=39.74,
        lon=-105.18,
        system_capacity_kw=4.0,
        state="CO",
        install_cost_usd=10_000,
        install_year=2026,
    )
    assert result.data["effective_rate_usd_per_kwh"] == pytest.approx(0.15)
    assert any("EIA state average" in w for w in result.warnings)
    assert any("EIA CO residential average" in a for a in result.assumptions)


@pytest.mark.anyio
async def test_tts_snapshot_supplies_default_cost(tmp_path: Path, client_for: ClientFor) -> None:
    """Phase 3 soft dependency: a synced Tracking the Sun table beats the constant."""
    store = BulkStore(path=":memory:")
    csv = tmp_path / "tts.csv"
    csv.write_text("state,price_per_watt\nCO,3.4\nCO,2.6\nAZ,2.2\n")
    store.load_csv("tts", "tts_systems", csv, vintage="2026-05")

    result = await estimate_roi(
        client_for(NREL),
        client_for(OPENEI),
        client_for(EIA),
        store,
        lat=39.74,
        lon=-105.18,
        system_capacity_kw=4.0,
        state="CO",
        install_year=2026,
    )
    assert result.data["gross_cost_usd"] == pytest.approx(3.0 * 4000)  # CO median 3.0 $/W
    assert any("Tracking the Sun snapshot" in a for a in result.assumptions)


@pytest.mark.anyio
async def test_conflicting_cost_inputs_rejected(client_for: ClientFor) -> None:
    with pytest.raises(BadInput, match="at most one"):
        await estimate_roi(
            client_for(NREL),
            client_for(OPENEI),
            client_for(EIA),
            BulkStore(path=":memory:"),
            lat=39.74,
            lon=-105.18,
            system_capacity_kw=4.0,
            install_cost_usd=10_000,
            cost_per_watt=3.0,
        )
