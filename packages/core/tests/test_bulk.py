from pathlib import Path

import pytest
from solar_mcp_core.bulk import BulkStore


@pytest.fixture
def store() -> BulkStore:
    return BulkStore(path=":memory:")


def write_csv(tmp_path: Path) -> Path:
    csv = tmp_path / "systems.csv"
    csv.write_text("state,year,price_per_watt\nCO,2024,3.10\nCO,2024,2.90\nAZ,2023,2.50\n")
    return csv


def test_load_csv_records_vintage_and_counts(store: BulkStore, tmp_path: Path) -> None:
    count = store.load_csv("tts", "tts_systems", write_csv(tmp_path), vintage="2024-09")
    assert count == 3
    info = store.vintage("tts")
    assert info is not None
    assert info.vintage == "2024-09"
    assert info.schema_version == 1
    assert info.loaded_at.endswith("Z")


def test_reload_replaces_table_and_vintage(store: BulkStore, tmp_path: Path) -> None:
    csv = write_csv(tmp_path)
    store.load_csv("tts", "tts_systems", csv, vintage="2023-09")
    store.load_csv("tts", "tts_systems", csv, vintage="2024-09")
    info = store.vintage("tts")
    assert info is not None and info.vintage == "2024-09"
    rows = store.query("SELECT count(*) FROM tts_systems")
    assert rows[0][0] == 3  # replaced, not appended


def test_query_with_bound_params(store: BulkStore, tmp_path: Path) -> None:
    store.load_csv("tts", "tts_systems", write_csv(tmp_path), vintage="2024-09")
    rows = store.query("SELECT median(price_per_watt) FROM tts_systems WHERE state = ?", ["CO"])
    assert rows[0][0] == pytest.approx(3.0)


def test_missing_vintage_is_none(store: BulkStore) -> None:
    assert store.vintage("nope") is None
    assert not store.has_table("nothing_here")


def test_invalid_table_identifier_rejected(store: BulkStore, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid table name"):
        store.load_csv("x", "bad;table", write_csv(tmp_path), vintage="v")
