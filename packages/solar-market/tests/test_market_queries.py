from pathlib import Path

import pytest
from market_test_data import CANONICAL_TTS, SOLARTRACE_CSV
from solar_mcp_core.bulk import BulkStore
from solar_mcp_core.errors import BadInput, SourceUnavailable
from solar_mcp_market.sync import load_solartrace, load_tracking_the_sun
from solar_mcp_market.tools.get_permitting_timelines import get_permitting_timelines
from solar_mcp_market.tools.query_installed_systems import query_installed_systems

from conftest import assert_envelope


@pytest.fixture
async def synced_store(tmp_path: Path) -> BulkStore:
    store = BulkStore(path=":memory:")
    tts = tmp_path / "tts.csv"
    tts.write_text(CANONICAL_TTS)
    await load_tracking_the_sun(store, source=str(tts), vintage="2024")
    st = tmp_path / "st.csv"
    st.write_text(SOLARTRACE_CSV)
    await load_solartrace(store, source=str(st), vintage="2025-H2")
    return store


@pytest.mark.anyio
async def test_installed_systems_aggregates(synced_store: BulkStore) -> None:
    result = await query_installed_systems(synced_store, state="CO")
    assert_envelope(result)
    assert result.data["system_count"] == 2
    assert result.data["median_price_per_watt"] == pytest.approx(3.25)
    assert result.data["top_modules"][0]["manufacturer"] == "Qcells"
    assert any("vintage 2024" in a for a in result.assumptions)
    assert any("aggregate" in a for a in result.assumptions)


@pytest.mark.anyio
async def test_installed_systems_year_filter_and_errors(synced_store: BulkStore) -> None:
    result = await query_installed_systems(synced_store, state="CO", year_start=2024)
    assert result.data["system_count"] == 1

    with pytest.raises(BadInput, match="year_start"):
        await query_installed_systems(synced_store, state="CO", year_start=2025, year_end=2024)
    with pytest.raises(SourceUnavailable, match="no Tracking the Sun records"):
        await query_installed_systems(synced_store, state="WY")


@pytest.mark.anyio
async def test_installed_systems_requires_sync() -> None:
    with pytest.raises(SourceUnavailable, match="sync_tracking_the_sun"):
        await query_installed_systems(BulkStore(path=":memory:"), state="CO")


@pytest.mark.anyio
async def test_permitting_by_state(synced_store: BulkStore) -> None:
    result = await get_permitting_timelines(synced_store, state="CO")
    assert_envelope(result)
    assert len(result.data["jurisdictions"]) == 2
    assert result.data["median_permit_days"] == pytest.approx(10.0)  # median(12, 8)
    assert any("2025-H2" in a for a in result.assumptions)


@pytest.mark.anyio
async def test_permitting_by_jurisdiction_match(synced_store: BulkStore) -> None:
    result = await get_permitting_timelines(synced_store, jurisdiction="denver")
    assert [j["jurisdiction"] for j in result.data["jurisdictions"]] == ["Denver"]
    assert result.data["median_permit_days"] == pytest.approx(8.0)


@pytest.mark.anyio
async def test_permitting_input_validation(synced_store: BulkStore) -> None:
    with pytest.raises(BadInput, match="exactly one"):
        await get_permitting_timelines(synced_store)
    with pytest.raises(BadInput, match="exactly one"):
        await get_permitting_timelines(synced_store, state="CO", jurisdiction="Denver")
    with pytest.raises(SourceUnavailable, match="no SolarTRACE rows"):
        await get_permitting_timelines(synced_store, jurisdiction="Atlantis")


@pytest.mark.anyio
async def test_like_metacharacters_do_not_overmatch(synced_store: BulkStore) -> None:
    with pytest.raises(SourceUnavailable, match="no SolarTRACE rows"):
        await get_permitting_timelines(synced_store, jurisdiction="%")
    with pytest.raises(SourceUnavailable, match="no SolarTRACE rows"):
        await get_permitting_timelines(synced_store, jurisdiction="_enver")
