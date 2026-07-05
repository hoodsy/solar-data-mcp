from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from solar_mcp_core.cache import HttpCache
from solar_mcp_core.config import USPVDB, SourceConfig
from solar_mcp_core.errors import BadInput
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_core.ratelimit import TokenBucket
from solar_mcp_market.models import validate_bbox
from solar_mcp_market.tools.find_utility_scale_projects import find_utility_scale_projects

from conftest import FakeTime, RoutedTransport, assert_envelope

ClientFor = Callable[[SourceConfig], SolarHttpClient]


def test_bbox_validation() -> None:
    box = validate_bbox([-105.5, 38.0, -104.0, 40.0])
    assert box.west == -105.5 and box.north == 40.0
    with pytest.raises(BadInput, match="4 numbers"):
        validate_bbox([1, 2, 3])
    with pytest.raises(BadInput, match="west < east"):
        validate_bbox([-104.0, 38.0, -105.5, 40.0])


@pytest.mark.anyio
async def test_colorado_projects_replay(client_for: ClientFor) -> None:
    result = await find_utility_scale_projects(
        client_for(USPVDB), state="CO", min_capacity_mw=100, limit=5
    )
    assert_envelope(result)
    projects = result.data["projects"]
    assert 1 <= len(projects) <= 5
    capacities = [p["capacity_mw_ac"] for p in projects]
    assert all(c >= 100 for c in capacities)
    assert capacities == sorted(capacities, reverse=True), "largest first"
    assert result.data["total_capacity_mw_ac"] == pytest.approx(sum(capacities), abs=0.5)
    assert all(p["state"] == "CO" for p in projects)


@pytest.mark.anyio
async def test_input_validation_before_http(client_for: ClientFor) -> None:
    client = client_for(USPVDB)
    with pytest.raises(BadInput, match="exactly one"):
        await find_utility_scale_projects(client)
    with pytest.raises(BadInput, match="exactly one"):
        await find_utility_scale_projects(client, state="CO", bbox=[-105, 38, -104, 40])
    with pytest.raises(BadInput, match="state"):
        await find_utility_scale_projects(client, state="ZZ")
    with pytest.raises(BadInput, match="limit"):
        await find_utility_scale_projects(client, state="CO", limit=1000)


@pytest.mark.anyio
async def test_postgrest_filter_syntax(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The wire format is PostgREST operators — pin it so refactors can't drift."""
    transport = RoutedTransport(lambda request: httpx.Response(200, json=[]))
    fake = FakeTime()
    client = SolarHttpClient(
        USPVDB,
        transport=transport,
        cache=HttpCache(path=tmp_path / "c.db", clock=fake.clock),
        bucket=TokenBucket.per_hour(600, clock=fake.clock, sleep=fake.sleep),
        sleep=fake.sleep,
    )

    from solar_mcp_core.errors import SourceUnavailable

    with pytest.raises(SourceUnavailable):  # empty result set -> no projects found
        await find_utility_scale_projects(
            client, bbox=[-105.5, 38.0, -104.0, 40.0], min_capacity_mw=50, limit=10
        )
    params = dict(transport.requests[0].url.params)
    assert params["and"] == "(xlong.gte.-105.5,xlong.lte.-104.0,ylat.gte.38.0,ylat.lte.40.0)"
    assert params["p_cap_ac"] == "gte.50"
    assert params["order"] == "p_cap_ac.desc.nullslast"
