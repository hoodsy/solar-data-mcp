from pathlib import Path

import pytest
from solar_mcp_core.bulk import BulkStore
from solar_mcp_core.errors import BadInput
from solar_mcp_economics.incentives import (
    federal_incentives,
    state_programs,
    sync_snapshot,
)
from solar_mcp_economics.tools.incentive_tools import get_incentives, sync_incentives

from conftest import assert_envelope

CSV = (
    "state,name,type,administrator,url,expiry\n"
    'CO,"Xcel Solar Rewards",performance,Xcel Energy,https://example.org/xcel,2027-12-31\n'
    'CO,"State Tax Exemption",tax exemption,State of Colorado,https://example.org/co,\n'
    'AZ,"APS Rebate",rebate,APS,https://example.org/aps,\n'
)


def write_csv(tmp_path: Path, content: str = CSV) -> Path:
    path = tmp_path / "dsire.csv"
    path.write_text(content)
    return path


def test_federal_table_reflects_install_year() -> None:
    assert "30%" in federal_incentives(2026)[0].value
    assert "22%" in federal_incentives(2034)[0].value


def test_sync_and_query_state_programs(tmp_path: Path) -> None:
    store = BulkStore(path=":memory:")
    assert sync_snapshot(store, write_csv(tmp_path), vintage="2026-06") == 3
    programs = state_programs(store, "CO")
    assert [p.name for p in programs] == ["State Tax Exemption", "Xcel Solar Rewards"]
    assert programs[1].expiry == "2027-12-31"
    assert state_programs(store, "WY") == []


def test_sync_rejects_missing_columns(tmp_path: Path) -> None:
    bad = write_csv(tmp_path, "state,name\nCO,Something\n")
    with pytest.raises(ValueError, match="missing expected columns"):
        sync_snapshot(BulkStore(path=":memory:"), bad, vintage="v")


def test_unsynced_store_returns_no_programs() -> None:
    assert state_programs(BulkStore(path=":memory:"), "CO") == []


@pytest.mark.anyio
async def test_get_incentives_unsynced_warns_but_serves_federal() -> None:
    result = await get_incentives(BulkStore(path=":memory:"), state="CO", install_year=2026)
    assert_envelope(result)
    assert result.data["federal"][0]["name"].startswith("Residential Clean Energy")
    assert result.data["state_local"] == []
    assert result.data["snapshot_vintage"] is None
    assert any("not synced" in w for w in result.warnings)


@pytest.mark.anyio
async def test_sync_then_get_incentives_cites_vintage(tmp_path: Path) -> None:
    store = BulkStore(path=":memory:")
    synced = await sync_incentives(store, source=str(write_csv(tmp_path)), vintage="2026-06")
    assert_envelope(synced, expect_assumptions=False)  # every input was explicit
    assert synced.data["rows_loaded"] == 3

    result = await get_incentives(store, state="CO", install_year=2026)
    assert len(result.data["state_local"]) == 2
    assert result.data["snapshot_vintage"] == "2026-06"
    assert any("vintage 2026-06" in a for a in result.assumptions)
    assert result.warnings == []


@pytest.mark.anyio
async def test_sync_rejects_missing_path() -> None:
    with pytest.raises(BadInput, match="source"):
        await sync_incentives(BulkStore(path=":memory:"), source="/nope/missing.csv")
