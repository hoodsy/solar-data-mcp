from pathlib import Path

import pytest
from solar_mcp_core.config import (
    CACHE_DIR_ENV,
    NREL,
    SOURCES,
    api_key_for,
    cache_dir,
    debug_enabled,
)


def test_nrel_source_registered() -> None:
    assert SOURCES["nrel"] is NREL
    assert NREL.rate_limit_per_hour == 1000
    assert NREL.cache_ttl_seconds == 30 * 86400
    assert NREL.api_key_env == "NREL_API_KEY"


def test_cache_dir_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(CACHE_DIR_ENV, str(tmp_path))
    assert cache_dir() == tmp_path


def test_cache_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CACHE_DIR_ENV, raising=False)
    assert cache_dir() == Path.home() / ".cache" / "solar-mcp"


def test_debug_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOLAR_MCP_DEBUG", raising=False)
    assert not debug_enabled()
    monkeypatch.setenv("SOLAR_MCP_DEBUG", "1")
    assert debug_enabled()


def test_api_key_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NREL_API_KEY", raising=False)
    assert api_key_for(NREL) is None
    monkeypatch.setenv("NREL_API_KEY", "")
    assert api_key_for(NREL) is None
    monkeypatch.setenv("NREL_API_KEY", "abc123")
    assert api_key_for(NREL) == "abc123"
