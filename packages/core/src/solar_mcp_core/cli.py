"""`solar-mcp` CLI. `doctor` checks keys and pings each registered source.

This is the one component that intentionally makes live API calls — it exists
so users can verify their setup before pointing an agent at a server.
"""

import argparse
import asyncio
import sys
from collections.abc import Callable

from solar_mcp_core.cache import HttpCache
from solar_mcp_core.config import SOURCES, SourceConfig, api_key_for, cache_dir
from solar_mcp_core.errors import QuotaExceeded, SourceUnavailable
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_core.ratelimit import TokenBucket

# Cheapest keyed endpoint per source, used as the liveness ping.
_PING: dict[str, tuple[str, dict[str, object]]] = {
    "nrel": ("/api/solar/solar_resource/v1.json", {"lat": 39.74, "lon": -105.18}),
}

# Test seam: tests swap this factory to inject a MockTransport-backed client.
ClientFactory = Callable[[SourceConfig], SolarHttpClient]


def _default_client_factory(config: SourceConfig) -> SolarHttpClient:
    return SolarHttpClient(
        config,
        # Doctor must observe the live source, not yesterday's cache entry:
        # a private bucket and throwaway cache keep it honest without
        # touching the shared cache DB's freshness.
        cache=HttpCache(path=cache_dir() / "doctor.db"),
        bucket=TokenBucket(capacity=5, refill_per_second=1),
    )


def doctor(client_factory: ClientFactory = _default_client_factory) -> int:
    ok = True
    print(f"cache dir: {cache_dir()} ({'writable' if _cache_writable() else 'NOT WRITABLE'})")
    for config in SOURCES.values():
        ok &= _check_source(config, client_factory)
    return 0 if ok else 1


def _check_source(config: SourceConfig, client_factory: ClientFactory) -> bool:
    label = f"[{config.name}]"
    key = api_key_for(config)
    if key is None:
        print(f"{label} FAIL — {config.api_key_env} not set. Get a free key: {config.signup_url}")
        return False
    print(f"{label} key present ({config.api_key_env})")

    path, params = _PING[config.name]
    try:
        result = asyncio.run(_ping(config, client_factory, path, params))
    except QuotaExceeded as exc:
        print(f"{label} FAIL — {exc}")
        return False
    except SourceUnavailable as exc:
        print(f"{label} FAIL — {exc.detail} (signup: {config.signup_url})")
        return False

    suffix = f", {result} requests remaining this hour" if result is not None else ""
    print(f"{label} PASS — live ping OK{suffix}")
    return True


async def _ping(
    config: SourceConfig,
    client_factory: ClientFactory,
    path: str,
    params: dict[str, object],
) -> int | None:
    client = client_factory(config)
    try:
        fetched = await client.get_json(path, dict(params))
        return fetched.ratelimit_remaining
    finally:
        await client.aclose()


def _cache_writable() -> bool:
    try:
        cache_dir().mkdir(parents=True, exist_ok=True)
        probe = cache_dir() / ".write-probe"
        probe.touch()
        probe.unlink()
        return True
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="solar-mcp", description="solar-data-mcp utilities")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check API keys and ping each data source")
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return doctor()
    return 2  # pragma: no cover — argparse enforces the choices


if __name__ == "__main__":
    sys.exit(main())
