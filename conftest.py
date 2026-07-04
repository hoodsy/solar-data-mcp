"""Root pytest configuration: fixture record/replay for every API source.

Replay (default, CI): every request resolves against fixtures/<source>/*.json
via an in-process transport — there is no real transport object anywhere, so
CI structurally cannot make a live call. An unknown request is a hard failure
that prints the missing key.

Record (local only): `uv run pytest --record` sends real requests (keys from
the environment or .env) and writes scrubbed fixtures into the subdirectory of
whichever registered source matches the request host.
"""

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from solar_mcp_core.cache import HttpCache, canonicalize
from solar_mcp_core.config import NREL, SOURCES, SourceConfig
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_core.ratelimit import TokenBucket

REPO_ROOT = Path(__file__).parent
FIXTURES_ROOT = REPO_ROOT / "fixtures"


def _source_dir_for_host(host: str | None) -> str:
    for config in SOURCES.values():
        if httpx.URL(config.base_url).host == host:
            return config.name
    return host or "unknown"


class FakeTime:
    """Clock + sleep pair for tests: sleeping advances the clock, no real waiting."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class ScriptedTransport(httpx.AsyncBaseTransport):
    """Returns queued responses in order; records every request it saw."""

    def __init__(self, responses: list[httpx.Response | Exception]) -> None:
        self.queue = list(responses)
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class RoutedTransport(httpx.AsyncBaseTransport):
    """Routes each request through a handler — for order-independent scripting
    (e.g. concurrent sweeps where response order is nondeterministic)."""

    def __init__(self, handler: "Callable[[httpx.Request], httpx.Response]") -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--record",
        action="store_true",
        default=False,
        help="hit live APIs and refresh fixtures (needs NREL_API_KEY in env or .env)",
    )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def request_key(request: httpx.Request) -> str:
    """Canonical fixture key for an outgoing request.

    Derived from the request URL (not the original params dict) so record and
    replay normalize identically regardless of how httpx serialized values.
    """
    params = {k: v for k, v in request.url.params.items()}
    return canonicalize(f"{request.url.scheme}://{request.url.host}", request.url.path, params)


class ReplayTransport(httpx.AsyncBaseTransport):
    """Serves recorded fixtures for every source; unknown requests fail loudly."""

    def __init__(self, fixtures_root: Path) -> None:
        self.index: dict[str, dict[str, Any]] = {}
        if fixtures_root.is_dir():
            for path in sorted(fixtures_root.glob("*/*.json")):
                recorded = json.loads(path.read_text())
                self.index[recorded["key"]] = recorded

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        key = request_key(request)
        recorded = self.index.get(key)
        if recorded is None:
            raise AssertionError(
                f"No fixture for request:\n  {key}\n"
                f"Known fixtures: {len(self.index)}. "
                "Run `uv run pytest --record` with NREL_API_KEY set to record it."
            )
        response = recorded["response"]
        return httpx.Response(
            status_code=response["status"],
            headers=response.get("headers", {}),
            json=response["json"],
        )


class RecordingTransport(httpx.AsyncBaseTransport):
    """Fetches and records only requests with no existing fixture.

    Already-recorded keys replay from disk, so a re-run after a quota hit
    (DEMO_KEY is 10 req/hr) only fetches what is still missing. Delete files
    from fixtures/ to force a genuine refresh.
    """

    def __init__(self, fixtures_root: Path) -> None:
        self.fixtures_root = fixtures_root
        self.inner = httpx.AsyncHTTPTransport()
        self.memo: dict[str, httpx.Response] = {}  # dedupe within one pytest run
        self.replay = ReplayTransport(fixtures_root)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        key = request_key(request)
        if key in self.replay.index:
            return await self.replay.handle_async_request(request)
        if key in self.memo:
            cached = self.memo[key]
            return httpx.Response(
                status_code=cached.status_code, headers=cached.headers, content=cached.content
            )
        response = await self.inner.handle_async_request(request)
        content = await response.aread()  # decoded bytes — drop encoding headers below
        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")
        }
        # 4xx bodies (e.g. out-of-coverage) replay too; 429 is transient, never a fixture
        if response.status_code < 500 and response.status_code != 429:
            self._write_fixture(key, request, response, content)
        self.memo[key] = httpx.Response(
            status_code=response.status_code, headers=headers, content=content
        )
        return httpx.Response(status_code=response.status_code, headers=headers, content=content)

    def _write_fixture(
        self, key: str, request: httpx.Request, response: httpx.Response, content: bytes
    ) -> None:
        body = json.loads(content)
        if isinstance(body.get("inputs"), dict) and "api_key" in body["inputs"]:
            body["inputs"]["api_key"] = "SCRUBBED"
        slug = request.url.path.strip("/").replace("/", "_").replace(".json", "")
        digest = hashlib.sha1(key.encode()).hexdigest()[:8]
        fixtures_dir = self.fixtures_root / _source_dir_for_host(request.url.host)
        fixtures_dir.mkdir(parents=True, exist_ok=True)
        fixture = {
            "key": key,
            "hand_authored": False,
            "response": {
                "status": response.status_code,
                "headers": {
                    k: v
                    for k, v in response.headers.items()
                    if k.lower() in ("x-ratelimit-remaining", "x-ratelimit-limit")
                },
                "json": body,
            },
        }
        (fixtures_dir / f"{slug}_{digest}.json").write_text(
            json.dumps(fixture, indent=2, sort_keys=True) + "\n"
        )


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, _, value = line.partition("=")
            if value:
                os.environ.setdefault(name.strip(), value.strip())


@pytest.fixture
def api_transport(request: pytest.FixtureRequest) -> httpx.AsyncBaseTransport:
    """One transport for all sources: fixture keys carry the full host."""
    if request.config.getoption("--record"):
        _load_dotenv(REPO_ROOT / ".env")
        return RecordingTransport(FIXTURES_ROOT)
    return ReplayTransport(FIXTURES_ROOT)


@pytest.fixture
def client_for(
    api_transport: httpx.AsyncBaseTransport,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> Callable[[SourceConfig], SolarHttpClient]:
    monkeypatch.setenv("SOLAR_MCP_CACHE_DIR", str(tmp_path))  # hermetic cache per test
    if not request.config.getoption("--record"):
        for config in SOURCES.values():  # key-presence code paths still run in replay
            if config.api_key_env is not None:
                monkeypatch.setenv(config.api_key_env, "TESTKEY")

    def make(config: SourceConfig) -> SolarHttpClient:
        return SolarHttpClient(
            config,
            transport=api_transport,
            cache=HttpCache(path=tmp_path / f"{config.name}.db"),
            bucket=TokenBucket(capacity=100, refill_per_second=10),
        )

    return make


@pytest.fixture
def nrel_client(client_for: Callable[[SourceConfig], SolarHttpClient]) -> SolarHttpClient:
    return client_for(NREL)
