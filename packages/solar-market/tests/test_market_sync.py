from pathlib import Path

import pytest
from packages_market_test_data import CANONICAL_TTS, SOLARTRACE_CSV
from solar_mcp_core.bulk import BulkStore
from solar_mcp_core.errors import BadInput
from solar_mcp_market.sync import load_solartrace, load_tracking_the_sun
from solar_mcp_market.tools.sync_tools import sync_solartrace, sync_tracking_the_sun

from conftest import assert_envelope

LBNL_TTS = "state,installed_price,system_size_DC,year\nCO,21000,7.0,2024\nAZ,16000,8.0,2023\n"


def csv_file(tmp_path: Path, content: str, name: str = "data.csv") -> Path:
    path = tmp_path / name
    path.write_text(content)
    return path


@pytest.mark.anyio
async def test_canonical_tts_loads(tmp_path: Path) -> None:
    store = BulkStore(path=":memory:")
    count = await load_tracking_the_sun(
        store, source=str(csv_file(tmp_path, CANONICAL_TTS)), vintage="2024"
    )
    assert count == 3
    rows = store.query("SELECT median(price_per_watt) FROM tts_systems WHERE state = 'CO'")
    assert rows[0][0] == pytest.approx(3.25)


@pytest.mark.anyio
async def test_lbnl_columns_derive_price_per_watt(tmp_path: Path) -> None:
    store = BulkStore(path=":memory:")
    await load_tracking_the_sun(store, source=str(csv_file(tmp_path, LBNL_TTS)), vintage="2024")
    rows = store.query("SELECT price_per_watt FROM tts_systems WHERE state = 'CO'")
    assert rows[0][0] == pytest.approx(3.0)  # 21000 / (7 kW * 1000)


@pytest.mark.anyio
async def test_state_filter_limits_rows(tmp_path: Path) -> None:
    store = BulkStore(path=":memory:")
    count = await load_tracking_the_sun(
        store, source=str(csv_file(tmp_path, CANONICAL_TTS)), vintage="2024", state="CO"
    )
    assert count == 2
    assert store.query("SELECT count(*) FROM tts_systems WHERE state = 'AZ'")[0][0] == 0


@pytest.mark.anyio
async def test_wrong_tts_columns_fail_loudly(tmp_path: Path) -> None:
    store = BulkStore(path=":memory:")
    bad = csv_file(tmp_path, "a,b\n1,2\n")
    with pytest.raises(BadInput, match="Tracking the Sun export"):
        await load_tracking_the_sun(store, source=str(bad), vintage="v")


@pytest.mark.anyio
async def test_solartrace_loads_and_validates(tmp_path: Path) -> None:
    store = BulkStore(path=":memory:")
    count = await load_solartrace(
        store, source=str(csv_file(tmp_path, SOLARTRACE_CSV)), vintage="2025-H2"
    )
    assert count == 3
    with pytest.raises(BadInput, match="SolarTRACE export"):
        await load_solartrace(
            store, source=str(csv_file(tmp_path, "state,foo\nCO,1\n")), vintage="v"
        )


@pytest.mark.anyio
async def test_sync_tools_return_envelopes(tmp_path: Path) -> None:
    store = BulkStore(path=":memory:")
    tts = await sync_tracking_the_sun(
        store, source=str(csv_file(tmp_path, CANONICAL_TTS)), state="co"
    )
    assert_envelope(tts)  # vintage defaulted -> assumption present
    assert tts.data["rows_loaded"] == 2
    assert tts.data["state_filter"] == "CO"

    solartrace = await sync_solartrace(
        store, source=str(csv_file(tmp_path, SOLARTRACE_CSV, "st.csv")), vintage="2025-H2"
    )
    assert_envelope(solartrace, expect_assumptions=False)
    assert solartrace.data["rows_loaded"] == 3


@pytest.mark.anyio
async def test_missing_source_path_rejected() -> None:
    with pytest.raises(BadInput, match="source"):
        await sync_solartrace(BulkStore(path=":memory:"), source="/nope.csv")
