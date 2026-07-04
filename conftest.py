"""Root pytest configuration: fixture record/replay for NREL tests.

Replay (default, CI): every request resolves against fixtures/nrel/*.json via
an in-process transport — there is no real transport object anywhere, so CI
structurally cannot make a live call. An unknown request is a hard failure
that prints the missing key.

Record (local only): `uv run pytest --record` sends real requests (key from
the environment or .env) and rewrites scrubbed fixtures.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest
from solar_mcp_core.cache import HttpCache, canonicalize
from solar_mcp_core.config import NREL
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_core.ratelimit import TokenBucket

REPO_ROOT = Path(__file__).parent
FIXTURES_DIR = REPO_ROOT / "fixtures" / "nrel"


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
    """Serves recorded fixtures; unknown requests fail the test loudly."""

    def __init__(self, fixtures_dir: Path) -> None:
        self.index: dict[str, dict[str, Any]] = {}
        if fixtures_dir.is_dir():
            for path in sorted(fixtures_dir.glob("*.json")):
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

    def __init__(self, fixtures_dir: Path) -> None:
        self.fixtures_dir = fixtures_dir
        self.inner = httpx.AsyncHTTPTransport()
        self.memo: dict[str, httpx.Response] = {}  # dedupe within one pytest run
        self.replay = ReplayTransport(fixtures_dir)

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
        self.fixtures_dir.mkdir(parents=True, exist_ok=True)
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
        (self.fixtures_dir / f"{slug}_{digest}.json").write_text(
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
def nrel_transport(request: pytest.FixtureRequest) -> httpx.AsyncBaseTransport:
    if request.config.getoption("--record"):
        _load_dotenv(REPO_ROOT / ".env")
        if not os.environ.get("NREL_API_KEY"):
            pytest.fail("--record needs NREL_API_KEY in the environment or .env")
        return RecordingTransport(FIXTURES_DIR)
    return ReplayTransport(FIXTURES_DIR)


@pytest.fixture
def nrel_client(
    nrel_transport: httpx.AsyncBaseTransport,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> SolarHttpClient:
    monkeypatch.setenv("SOLAR_MCP_CACHE_DIR", str(tmp_path))  # hermetic cache per test
    if not request.config.getoption("--record"):
        monkeypatch.setenv("NREL_API_KEY", "TESTKEY")  # key-presence code paths still run
    return SolarHttpClient(
        NREL,
        transport=nrel_transport,
        cache=HttpCache(path=tmp_path / "http.db"),
        bucket=TokenBucket(capacity=100, refill_per_second=10),
    )
