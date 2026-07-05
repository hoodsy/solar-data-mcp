import json
from pathlib import Path

import httpx
import pytest
from solar_mcp_core.cache import HttpCache
from solar_mcp_core.config import NREL
from solar_mcp_core.errors import QuotaExceeded, SourceUnavailable
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_core.ratelimit import TokenBucket

from conftest import FakeTime, ScriptedTransport, build_client


def make_client(
    tmp_path: Path,
    transport: httpx.AsyncBaseTransport,
    fake: FakeTime,
) -> SolarHttpClient:
    return build_client(NREL, transport, tmp_path, fake)


def ok(body: dict[str, object], remaining: str = "999") -> httpx.Response:
    return httpx.Response(200, json=body, headers={"X-RateLimit-Remaining": remaining})


@pytest.mark.anyio
async def test_success_is_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NREL_API_KEY", "TESTKEY")
    fake = FakeTime()
    transport = ScriptedTransport([ok({"outputs": {"x": 1}})])
    client = make_client(tmp_path, transport, fake)

    first = await client.get_json("/api/pvwatts/v8.json", {"lat": 40, "lon": -105})
    assert first.data == {"outputs": {"x": 1}}
    assert not first.from_cache
    assert first.ratelimit_remaining == 999
    assert "api_key" not in first.url

    second = await client.get_json("/api/pvwatts/v8.json", {"lat": 40, "lon": -105})
    assert second.from_cache
    assert second.data == first.data
    assert len(transport.requests) == 1  # second call never hit the network


@pytest.mark.anyio
async def test_api_key_sent_but_not_in_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NREL_API_KEY", "SECRETKEY")
    fake = FakeTime()
    transport = ScriptedTransport([ok({})])
    client = make_client(tmp_path, transport, fake)

    result = await client.get_json("/api/x", {"lat": 40})
    assert "SECRETKEY" in str(transport.requests[0].url)
    assert "SECRETKEY" not in result.url


@pytest.mark.anyio
async def test_retry_then_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NREL_API_KEY", "TESTKEY")
    fake = FakeTime()
    transport = ScriptedTransport([httpx.Response(500), httpx.Response(503), ok({"fine": True})])
    client = make_client(tmp_path, transport, fake)

    result = await client.get_json("/api/x", {"lat": 40})
    assert result.data == {"fine": True}
    assert fake.slept == [1.0, 2.0]


@pytest.mark.anyio
async def test_retry_exhaustion_raises_source_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NREL_API_KEY", "TESTKEY")
    fake = FakeTime()
    transport = ScriptedTransport([httpx.Response(500), httpx.Response(500), httpx.Response(500)])
    client = make_client(tmp_path, transport, fake)

    with pytest.raises(SourceUnavailable, match="HTTP 500 after 3 attempts"):
        await client.get_json("/api/x", {"lat": 40})


@pytest.mark.anyio
async def test_transport_errors_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NREL_API_KEY", "TESTKEY")
    fake = FakeTime()
    transport = ScriptedTransport([httpx.ConnectTimeout("boom"), ok({"recovered": True})])
    client = make_client(tmp_path, transport, fake)

    result = await client.get_json("/api/x", {"lat": 40})
    assert result.data == {"recovered": True}


@pytest.mark.anyio
async def test_retry_after_header_honored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NREL_API_KEY", "TESTKEY")
    fake = FakeTime()
    transport = ScriptedTransport([httpx.Response(503, headers={"Retry-After": "7"}), ok({})])
    client = make_client(tmp_path, transport, fake)

    await client.get_json("/api/x", {"lat": 40})
    assert fake.slept == [7.0]  # Retry-After beats the 1s backoff


@pytest.mark.anyio
async def test_429_raises_quota_exceeded_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NREL_API_KEY", "TESTKEY")
    fake = FakeTime()
    transport = ScriptedTransport([httpx.Response(429, headers={"X-RateLimit-Remaining": "0"})])
    client = make_client(tmp_path, transport, fake)

    with pytest.raises(QuotaExceeded) as excinfo:
        await client.get_json("/api/x", {"lat": 40})
    assert excinfo.value.remaining == 0
    assert len(transport.requests) == 1  # never retried
    assert fake.slept == []


@pytest.mark.anyio
async def test_429_serves_stale_cache_when_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NREL_API_KEY", "TESTKEY")
    fake = FakeTime()
    transport = ScriptedTransport([ok({"v": 1}), httpx.Response(429)])
    client = make_client(tmp_path, transport, fake)

    await client.get_json("/api/x", {"lat": 40})
    fake.now += NREL.cache_ttl_seconds + 1  # entry is now stale

    result = await client.get_json("/api/x", {"lat": 40})
    assert result.data == {"v": 1}
    assert result.from_cache
    assert result.stale


@pytest.mark.anyio
async def test_403_names_the_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NREL_API_KEY", "BADKEY")
    fake = FakeTime()
    transport = ScriptedTransport([httpx.Response(403)])
    client = make_client(tmp_path, transport, fake)

    with pytest.raises(SourceUnavailable, match="NREL_API_KEY"):
        await client.get_json("/api/x", {"lat": 40})


@pytest.mark.anyio
async def test_cache_body_round_trips_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NREL_API_KEY", "TESTKEY")
    fake = FakeTime()
    payload = {"outputs": {"ac_annual": 6543.21, "ac_monthly": [1.0] * 12}}
    transport = ScriptedTransport([httpx.Response(200, text=json.dumps(payload))])
    client = make_client(tmp_path, transport, fake)

    await client.get_json("/api/x", {"lat": 40})
    cached = await client.get_json("/api/x", {"lat": 40})
    assert cached.data == payload


@pytest.mark.anyio
async def test_non_json_200_not_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A garbage 200 body (proxy hiccup) must raise cleanly and must NOT poison the cache."""
    monkeypatch.setenv("NREL_API_KEY", "TESTKEY")
    fake = FakeTime()
    transport = ScriptedTransport(
        [httpx.Response(200, text="<html>captive portal</html>"), ok({"fine": True})]
    )
    client = make_client(tmp_path, transport, fake)

    with pytest.raises(SourceUnavailable, match="non-JSON response"):
        await client.get_json("/api/x", {"lat": 40})

    result = await client.get_json("/api/x", {"lat": 40})  # retry hits network, not cache
    assert result.data == {"fine": True}
    assert not result.from_cache


@pytest.mark.anyio
async def test_4xx_body_redacts_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NREL_API_KEY", "SECRETKEY")
    fake = FakeTime()
    transport = ScriptedTransport(
        [httpx.Response(422, text='{"inputs": {"api_key": "SECRETKEY"}, "errors": ["bad"]}')]
    )
    client = make_client(tmp_path, transport, fake)

    with pytest.raises(SourceUnavailable) as excinfo:
        await client.get_json("/api/x", {"lat": 40})
    assert "SECRETKEY" not in str(excinfo.value)
    assert "REDACTED" in str(excinfo.value)


@pytest.mark.anyio
async def test_token_header_auth_style(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = NREL.model_copy(update={"auth_style": "token_header", "api_key_env": "AHJ_TOKEN"})
    monkeypatch.setenv("AHJ_TOKEN", "SECRETTOKEN")
    fake = FakeTime()
    transport = ScriptedTransport([ok({})])
    client = SolarHttpClient(
        config,
        transport=transport,
        cache=HttpCache(path=tmp_path / "http.db", clock=fake.clock),
        bucket=TokenBucket.per_hour(1000, clock=fake.clock, sleep=fake.sleep),
        sleep=fake.sleep,
    )

    result = await client.get_json("/api/x", {"lat": 40})
    sent = transport.requests[0]
    assert sent.headers["Authorization"] == "Token SECRETTOKEN"
    assert "SECRETTOKEN" not in str(sent.url)  # never in the query string
    assert "SECRETTOKEN" not in result.url


@pytest.mark.anyio
async def test_unauthenticated_source_sends_no_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = NREL.model_copy(update={"auth_style": "none", "api_key_env": None})
    fake = FakeTime()
    transport = ScriptedTransport([ok({})])
    client = SolarHttpClient(
        config,
        transport=transport,
        cache=HttpCache(path=tmp_path / "http.db", clock=fake.clock),
        bucket=TokenBucket.per_hour(1000, clock=fake.clock, sleep=fake.sleep),
        sleep=fake.sleep,
    )

    await client.get_json("/api/x", {"lat": 40})
    sent = transport.requests[0]
    assert "api_key" not in str(sent.url)
    assert "Authorization" not in sent.headers
