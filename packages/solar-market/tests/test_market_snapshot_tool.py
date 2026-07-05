from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from market_test_data import CANONICAL_TTS
from solar_mcp_core.bulk import BulkStore
from solar_mcp_core.config import USPVDB, SourceConfig
from solar_mcp_core.errors import SourceUnavailable
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_market.sync import load_tracking_the_sun
from solar_mcp_market.tools.market_snapshot import market_snapshot

from conftest import assert_envelope, build_client

ClientFor = Callable[[SourceConfig], SolarHttpClient]


@pytest.mark.anyio
async def test_snapshot_partial_sections_with_warnings(
    tmp_path: Path, client_for: ClientFor
) -> None:
    """TTS synced + USPVDB live (replay); SolarTRACE missing -> warning, not failure."""
    store = BulkStore(path=":memory:")
    csv = tmp_path / "tts.csv"
    csv.write_text(CANONICAL_TTS)
    await load_tracking_the_sun(store, source=str(csv), vintage="2024")

    result = await market_snapshot(client_for(USPVDB), store, state="CO")
    assert_envelope(result)
    assert result.data["installed_systems"]["system_count"] == 2
    assert "permitting" not in result.data
    assert any("permitting unavailable" in w for w in result.warnings)
    assert result.data["utility_scale"]["largest_projects"]
    components = {entry["component"] for entry in result.data["audit_trail"]}
    assert components == {"installed_systems", "utility_scale"}


@pytest.mark.anyio
async def test_snapshot_fails_only_when_everything_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOLAR_DATA_MCP_CACHE_DIR", str(tmp_path))
    client = build_client(USPVDB, lambda request: httpx.Response(500), tmp_path)

    with pytest.raises(SourceUnavailable, match="no market data available"):
        await market_snapshot(client, BulkStore(path=":memory:"), state="CO")
