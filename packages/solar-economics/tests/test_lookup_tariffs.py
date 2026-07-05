from collections.abc import Callable

import httpx
import pytest
from solar_mcp_core.config import OPENEI, SourceConfig
from solar_mcp_core.errors import BadInput, SourceUnavailable
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_economics.tools.lookup_tariffs import lookup_tariffs

from conftest import assert_envelope

ClientFor = Callable[[SourceConfig], SolarHttpClient]


@pytest.mark.anyio
async def test_lookup_tariffs_boulder_replay(client_for: ClientFor) -> None:
    result = await lookup_tariffs(client_for(OPENEI), lat=39.74, lon=-105.18)
    assert_envelope(result)
    assert result.data["utilities"], "expected at least one utility serving Boulder"
    tariffs = result.data["tariffs"]
    assert tariffs
    for tariff in tariffs:
        if not tariff["is_tou"] and tariff["first_tier_rate_usd_per_kwh"] is not None:
            assert 0.01 < tariff["first_tier_rate_usd_per_kwh"] < 1.0  # sane $/kWh
    assert any("sector not provided" in a for a in result.assumptions)
    assert result.source.name.startswith("OpenEI")


@pytest.mark.anyio
async def test_requires_exactly_one_location_mode(client_for: ClientFor) -> None:
    client = client_for(OPENEI)
    with pytest.raises(BadInput, match="exactly one"):
        await lookup_tariffs(client)  # neither
    with pytest.raises(BadInput, match="exactly one"):
        await lookup_tariffs(client, lat=39.74, lon=-105.18, utility_name="Xcel")  # both
    with pytest.raises(BadInput, match="exactly one"):
        await lookup_tariffs(client, lat=39.74)  # lat without lon


@pytest.mark.anyio
async def test_bad_sector_rejected_before_http(client_for: ClientFor) -> None:
    with pytest.raises(BadInput, match="sector"):
        await lookup_tariffs(client_for(OPENEI), lat=39.74, lon=-105.18, sector="farm")


@pytest.mark.anyio
async def test_utility_filter_is_enforced_client_side(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Upstream utility_name matching is fuzzy; the tool must post-filter."""
    from pathlib import Path

    from solar_mcp_core.cache import HttpCache
    from solar_mcp_core.ratelimit import TokenBucket

    from conftest import FakeTime, RoutedTransport

    monkeypatch.setenv("OPENEI_API_KEY", "TESTKEY")
    body = {
        "items": [
            {
                "utility": "Public Service Co of Colorado",
                "name": "Rate Match",
                "sector": "Residential",
                "uri": "u1",
                "energyratestructure": [[{"rate": 0.12}]],
            },
            {
                "utility": "Some Other Utility",
                "name": "Rate Noise",
                "sector": "Residential",
                "uri": "u2",
                "energyratestructure": [[{"rate": 0.55}]],
            },
        ]
    }
    fake = FakeTime()
    assert isinstance(tmp_path, Path)
    client = SolarHttpClient(
        OPENEI,
        transport=RoutedTransport(lambda request: httpx.Response(200, json=body)),
        cache=HttpCache(path=tmp_path / "c.db", clock=fake.clock),
        bucket=TokenBucket.per_hour(1000, clock=fake.clock, sleep=fake.sleep),
        sleep=fake.sleep,
    )

    result = await lookup_tariffs(client, utility_name="Public Service")
    names = [t["name"] for t in result.data["tariffs"]]
    assert names == ["Rate Match"]

    with pytest.raises(SourceUnavailable, match="no approved"):
        await lookup_tariffs(client, utility_name="Utility That Matches Nothing")
