from pathlib import Path

import httpx
import pytest
from solar_mcp_core.cache import HttpCache
from solar_mcp_core.cli import ClientFactory, doctor, main
from solar_mcp_core.config import SourceConfig
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_core.ratelimit import TokenBucket
from support import FakeTime, ScriptedTransport


def factory_for(transport: httpx.AsyncBaseTransport, tmp_path: Path) -> ClientFactory:
    fake = FakeTime()

    def factory(config: SourceConfig) -> SolarHttpClient:
        return SolarHttpClient(
            config,
            transport=transport,
            cache=HttpCache(path=tmp_path / "doctor.db", clock=fake.clock),
            bucket=TokenBucket(capacity=5, refill_per_second=1, sleep=fake.sleep),
            sleep=fake.sleep,
        )

    return factory


def test_doctor_fails_without_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SOLAR_MCP_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("NREL_API_KEY", raising=False)

    exit_code = doctor(factory_for(ScriptedTransport([]), tmp_path))
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "NREL_API_KEY not set" in out
    assert "https://developer.nlr.gov/signup/" in out


def test_doctor_passes_with_valid_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SOLAR_MCP_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("NREL_API_KEY", "GOODKEY")
    transport = ScriptedTransport(
        [httpx.Response(200, json={"outputs": {}}, headers={"X-RateLimit-Remaining": "997"})]
    )

    exit_code = doctor(factory_for(transport, tmp_path))
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "[nrel] PASS" in out
    assert "997 requests remaining" in out
    assert "cache dir" in out


def test_doctor_reports_invalid_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SOLAR_MCP_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("NREL_API_KEY", "BADKEY")
    transport = ScriptedTransport([httpx.Response(403)])

    exit_code = doctor(factory_for(transport, tmp_path))
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "[nrel] FAIL" in out
    assert "NREL_API_KEY" in out


def test_doctor_reports_quota(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SOLAR_MCP_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("NREL_API_KEY", "GOODKEY")
    transport = ScriptedTransport([httpx.Response(429, headers={"X-RateLimit-Remaining": "0"})])

    exit_code = doctor(factory_for(transport, tmp_path))
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "rate limit exceeded" in out


def test_main_requires_subcommand() -> None:
    with pytest.raises(SystemExit):
        main([])
