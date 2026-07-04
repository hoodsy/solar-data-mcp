from pathlib import Path

import httpx
import pytest
from helpers import assert_envelope
from solar_mcp_core.cache import HttpCache
from solar_mcp_core.config import NREL
from solar_mcp_core.errors import BadInput, SourceUnavailable
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_core.ratelimit import TokenBucket
from solar_mcp_nrel.tools.get_solar_resource import get_solar_resource, resolved_cell

from conftest import FakeTime, ScriptedTransport


def test_resolved_cell_is_grid_center() -> None:
    assert resolved_cell(39.74, -105.18) == (39.7, -105.2)
    assert resolved_cell(40.0, -105.0) == (40.0, -105.0)


@pytest.mark.anyio
async def test_get_solar_resource_boulder(nrel_client: SolarHttpClient) -> None:
    result = await get_solar_resource(nrel_client, lat=39.74, lon=-105.18)
    assert_envelope(result)
    assert 3 < result.data["ghi_annual"] < 8  # kWh/m2/day, sane for Colorado
    assert len(result.data["ghi_monthly"]) == 12
    assert result.data["resolved_cell_lat"] == 39.7
    assert any("0.1 deg" in a for a in result.assumptions)
    assert result.units["ghi_annual"] == "kWh/m2/day"


@pytest.mark.anyio
async def test_get_solar_resource_out_of_coverage(nrel_client: SolarHttpClient) -> None:
    with pytest.raises(SourceUnavailable):
        await get_solar_resource(nrel_client, lat=48.85, lon=2.35)  # Paris


@pytest.mark.anyio
async def test_get_solar_resource_rejects_bad_coords(nrel_client: SolarHttpClient) -> None:
    with pytest.raises(BadInput, match="lat"):
        await get_solar_resource(nrel_client, lat=91.0, lon=0.0)


@pytest.mark.anyio
async def test_single_missing_series_becomes_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One series 'no data' (live out-of-edge shape) -> partial result + warning."""
    monkeypatch.setenv("NREL_API_KEY", "TESTKEY")
    fake = FakeTime()
    body = {
        "errors": [],
        "warnings": [],
        "outputs": {
            "avg_ghi": {"annual": 4.8, "monthly": {"jan": 4.8, "feb": 4.9}},
            "avg_dni": "no data",
        },
    }
    client = SolarHttpClient(
        NREL,
        transport=ScriptedTransport([httpx.Response(200, json=body)]),
        cache=HttpCache(path=tmp_path / "http.db", clock=fake.clock),
        bucket=TokenBucket.per_hour(1000, clock=fake.clock, sleep=fake.sleep),
        sleep=fake.sleep,
    )

    result = await get_solar_resource(client, lat=39.74, lon=-105.18)
    assert result.data["ghi_annual"] == 4.8
    assert "dni_annual" not in result.data
    assert any("DNI not available" in w for w in result.warnings)
