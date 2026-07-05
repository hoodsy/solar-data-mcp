"""HTTP client all solar-data-mcp traffic goes through.

Order of operations per request: cache lookup → token bucket → HTTP with
retry/backoff → cache store. A 429 is never retried (NREL's window is rolling,
so retries only burn quota); instead the stale cache is served when available.

The ``transport`` constructor argument is the test seam: fixture replay injects
an ``httpx.MockTransport`` here, so tests exercise this exact code path with no
real network access possible.
"""

import asyncio
import json
import logging
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, NoReturn

import httpx

from solar_mcp_core.cache import HttpCache, canonicalize
from solar_mcp_core.config import SourceConfig, api_key_for, debug_enabled
from solar_mcp_core.envelope import SourceRef
from solar_mcp_core.errors import QuotaExceeded, SourceUnavailable
from solar_mcp_core.ratelimit import TokenBucket

_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (1.0, 2.0, 4.0)

logger = logging.getLogger("solar_mcp.http")


def configure_debug_logging() -> None:
    """Install the stderr debug handler when SOLAR_MCP_DEBUG=1.

    Called from process entry points (server main, CLI) rather than library
    constructors, so importing or instantiating a client has no logging side
    effects. stderr only — stdout belongs to the stdio MCP transport.
    """
    if debug_enabled() and not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(name)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class FetchedResponse:
    """Parsed JSON plus the provenance details tools need for SourceRef."""

    data: Any  # parsed JSON — an object for most sources, an array for PostgREST ones
    url: str  # canonical URL, api_key excluded
    retrieved_at: str  # ISO 8601 UTC
    from_cache: bool
    stale: bool
    ratelimit_remaining: int | None


def source_ref(name: str, fetched: FetchedResponse, license_note: str) -> SourceRef:
    """The SourceRef every tool builds from a fetch — one honest recipe."""
    return SourceRef(
        name=name, url=fetched.url, retrieved_at=fetched.retrieved_at, license=license_note
    )


def freshness_warnings(fetched: FetchedResponse) -> list[str]:
    if fetched.stale:
        return [
            "Served from an expired cache entry because the source's rate limit is "
            "exhausted; values may be out of date."
        ]
    return []


class SolarHttpClient:
    def __init__(
        self,
        config: SourceConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        cache: HttpCache | None = None,
        bucket: TokenBucket | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.config = config
        self._owns_cache = cache is None
        self._cache = cache if cache is not None else HttpCache()
        self._bucket = (
            bucket if bucket is not None else TokenBucket.per_hour(config.rate_limit_per_hour)
        )
        self._sleep = sleep
        self._client = httpx.AsyncClient(
            base_url=config.base_url, transport=transport, timeout=30.0, follow_redirects=True
        )
        # httpx's own INFO logging prints full request URLs — including api_key.
        # Our debug logs redact the key; make sure httpx can't leak it either.
        logging.getLogger("httpx").setLevel(logging.WARNING)

    async def get_json(self, path: str, params: dict[str, Any]) -> FetchedResponse:
        key = canonicalize(self.config.base_url, path, params)

        cached = self._cache.get(key)
        if cached is not None:
            logger.debug("cache hit %s", key)
            return FetchedResponse(
                data=json.loads(cached.body),
                url=key,
                retrieved_at=_iso(cached.retrieved_at),
                from_cache=True,
                stale=False,
                ratelimit_remaining=None,
            )
        logger.debug("cache miss %s", key)

        await self._bucket.acquire()
        try:
            response = await self._request_with_retry(path, params, key)
        except _StaleAvailable as stale_hit:
            return FetchedResponse(
                data=json.loads(stale_hit.body),
                url=key,
                retrieved_at=_iso(stale_hit.retrieved_at),
                from_cache=True,
                stale=True,
                ratelimit_remaining=None,
            )

        remaining = _remaining_header(response)
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as exc:
            # Never cache an unparseable body — a single proxy hiccup would
            # otherwise poison this key for the whole TTL.
            raise SourceUnavailable(
                self.config.name,
                f"non-JSON response (HTTP {response.status_code}): {response.text[:120]!r}",
            ) from exc
        entry = self._cache.put(
            key,
            source=self.config.name,
            status=response.status_code,
            body=response.text,
            ttl_seconds=self.config.cache_ttl_seconds,
        )
        return FetchedResponse(
            data=data,
            url=key,
            retrieved_at=_iso(entry.retrieved_at),
            from_cache=False,
            stale=False,
            ratelimit_remaining=remaining,
        )

    async def _request_with_retry(
        self, path: str, params: dict[str, Any], key: str
    ) -> httpx.Response:
        send_params = dict(params)
        headers: dict[str, str] = {}
        api_key = api_key_for(self.config)
        if api_key is not None:
            if self.config.auth_style == "api_key_param":
                send_params["api_key"] = api_key
            elif self.config.auth_style == "token_header":
                headers["Authorization"] = f"Token {api_key}"

        last_detail = "no attempts made"
        for attempt in range(_MAX_ATTEMPTS):
            retry_after: float | None = None
            try:
                response = await self._client.get(path, params=send_params, headers=headers)
            except httpx.TransportError as exc:
                last_detail = f"{type(exc).__name__}: {exc}"
                logger.debug("attempt %d transport error: %s", attempt + 1, last_detail)
            else:
                logger.debug(
                    "attempt %d HTTP %d remaining=%s",
                    attempt + 1,
                    response.status_code,
                    response.headers.get("X-RateLimit-Remaining"),
                )
                if response.status_code == 429:
                    self._handle_quota(response, key)
                if response.status_code < 500:
                    if response.status_code >= 400:
                        raise SourceUnavailable(
                            self.config.name, _client_error_detail(response, self.config)
                        )
                    return response
                last_detail = f"HTTP {response.status_code}"
                retry_after = _retry_after(response)

            if attempt < _MAX_ATTEMPTS - 1:
                await self._sleep(max(_BACKOFF_SECONDS[attempt], retry_after or 0.0))

        raise SourceUnavailable(self.config.name, f"{last_detail} after {_MAX_ATTEMPTS} attempts")

    def _handle_quota(self, response: httpx.Response, key: str) -> NoReturn:
        stale = self._cache.get(key, allow_stale=True)
        if stale is not None:
            logger.debug("quota exceeded; serving stale cache for %s", key)
            raise _StaleAvailable(stale.body, stale.retrieved_at)
        raise QuotaExceeded(self.config.name, remaining=_remaining_header(response))

    async def aclose(self) -> None:
        await self._client.aclose()
        if self._owns_cache:
            self._cache.close()


class _StaleAvailable(Exception):
    """Internal signal: quota hit but a stale cache entry exists."""

    def __init__(self, body: str, retrieved_at: float) -> None:
        self.body = body
        self.retrieved_at = retrieved_at
        super().__init__("stale cache available")


def _remaining_header(response: httpx.Response) -> int | None:
    raw = response.headers.get("X-RateLimit-Remaining")
    try:
        return int(raw) if raw is not None else None
    except ValueError:
        return None


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    try:
        return float(raw) if raw is not None else None
    except ValueError:
        return None


def _client_error_detail(response: httpx.Response, config: SourceConfig) -> str:
    if response.status_code == 403 and config.api_key_env is not None:
        hint = f" (get a free key: {config.signup_url})" if config.signup_url else ""
        return f"HTTP 403 — API key rejected; check {config.api_key_env}{hint}"
    body = response.text[:200]
    api_key = api_key_for(config)
    if api_key:  # error bodies can echo request inputs, including the key
        body = body.replace(api_key, "REDACTED")
    return f"HTTP {response.status_code}: {body}"
