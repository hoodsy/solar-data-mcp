from collections.abc import Callable
from pathlib import Path

import pytest
from solar_mcp_core.cache import HttpCache
from solar_mcp_core.config import AHJ, SourceConfig
from solar_mcp_core.errors import BadInput, SourceUnavailable
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_market.tools.identify_ahj import identify_ahj

from conftest import assert_envelope

ClientFor = Callable[[SourceConfig], SolarHttpClient]


@pytest.mark.anyio
async def test_identify_ahj_replay(client_for: ClientFor) -> None:
    result = await identify_ahj(client_for(AHJ), lat=39.74, lon=-105.18)
    assert_envelope(result)
    assert result.data["ahj_count"] == 1
    ahj = result.data["ahjs"][0]
    assert ahj["name"] == "Boulder County"
    assert ahj["electric_code"] == "2023 NEC"
    assert any("verify locally" in a for a in result.assumptions)


@pytest.mark.anyio
async def test_missing_token_degrades_with_instructions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AHJ_REGISTRY_TOKEN", raising=False)
    client = SolarHttpClient(AHJ, cache=HttpCache(path=tmp_path / "c.db"))

    with pytest.raises(SourceUnavailable) as excinfo:
        await identify_ahj(client, lat=39.74, lon=-105.18)
    message = str(excinfo.value)
    assert "support@sunspec.org" in message
    assert "AHJ_REGISTRY_TOKEN" in message
    await client.aclose()


@pytest.mark.anyio
async def test_coords_validated_before_token_check(client_for: ClientFor) -> None:
    with pytest.raises(BadInput, match="lat"):
        await identify_ahj(client_for(AHJ), lat=95.0, lon=0.0)
