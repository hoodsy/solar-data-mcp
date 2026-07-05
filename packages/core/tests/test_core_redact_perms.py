"""F3/F4: the api_key never reaches the on-disk cache or the returned envelope,
and cache files/dirs are owner-only."""

import json
import os
import sqlite3
import stat
from pathlib import Path

import httpx
import pytest
from solar_mcp_core.config import EIA, ensure_private_dir, harden_file_perms
from solar_mcp_core.redact import REDACTED, scrub_secret

from conftest import ScriptedTransport, build_client


def test_scrub_secret_raw_and_url_encoded() -> None:
    key = "abc/123+xyz"
    text = "raw=abc/123+xyz enc=abc%2F123%2Bxyz"
    out = scrub_secret(text, key)
    assert "abc/123+xyz" not in out
    assert "abc%2F123%2Bxyz" not in out
    assert out.count(REDACTED) == 2


def test_scrub_secret_noop_on_empty() -> None:
    assert scrub_secret("unchanged", None) == "unchanged"
    assert scrub_secret("unchanged", "") == "unchanged"


@pytest.mark.anyio
async def test_api_key_not_persisted_or_returned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EIA echoes the request api_key in its body; it must be scrubbed before it
    reaches the SQLite cache or the FetchedResponse."""
    monkeypatch.setenv("SOLAR_DATA_MCP_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("EIA_API_KEY", "SECRETKEY123")
    body = json.dumps(
        {"request": {"params": {"api_key": "SECRETKEY123"}}, "response": {"data": []}}
    )
    transport = ScriptedTransport([httpx.Response(200, text=body)])
    client = build_client(EIA, transport, tmp_path)
    try:
        fetched = await client.get_json("/v2/electricity/x", {"length": 1})
    finally:
        pass
    assert "SECRETKEY123" not in json.dumps(fetched.data)

    rows = sqlite3.connect(tmp_path / "eia.db").execute("SELECT body FROM http_cache").fetchall()
    assert rows, "response should have been cached"
    assert "SECRETKEY123" not in rows[0][0]
    assert REDACTED in rows[0][0]
    await client.aclose()


def test_ensure_private_dir_is_owner_only(tmp_path: Path) -> None:
    target = tmp_path / "cache"
    ensure_private_dir(target)
    assert target.is_dir()
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o700


def test_harden_file_perms_owner_only(tmp_path: Path) -> None:
    f = tmp_path / "http.db"
    f.write_text("x")
    harden_file_perms(f)
    if os.name == "posix":
        assert stat.S_IMODE(f.stat().st_mode) == 0o600
