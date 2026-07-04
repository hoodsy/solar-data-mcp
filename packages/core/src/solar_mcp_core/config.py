"""Per-source configuration registry.

Each data source gets one SourceConfig describing where it lives, how it
authenticates, how hard we may hit it, and how long responses stay fresh.
The registry lives in core so `solar-mcp doctor` can iterate every known
source without importing server packages.
"""

import os
from pathlib import Path

from pydantic import BaseModel

CACHE_DIR_ENV = "SOLAR_MCP_CACHE_DIR"
DEBUG_ENV = "SOLAR_MCP_DEBUG"


class SourceConfig(BaseModel):
    name: str
    base_url: str
    api_key_env: str
    rate_limit_per_hour: int
    cache_ttl_seconds: int
    license_note: str
    docs_url: str
    signup_url: str


NREL = SourceConfig(
    name="nrel",
    base_url="https://developer.nrel.gov",
    api_key_env="NREL_API_KEY",
    rate_limit_per_hour=1000,
    cache_ttl_seconds=30 * 86400,  # TMY results are deterministic per location+params
    license_note="NREL Developer Network — free API, attribution appreciated",
    docs_url="https://developer.nrel.gov/docs/solar/",
    signup_url="https://developer.nrel.gov/signup/",
)

SOURCES: dict[str, SourceConfig] = {NREL.name: NREL}


def cache_dir() -> Path:
    """Cache directory: $SOLAR_MCP_CACHE_DIR or ~/.cache/solar-mcp."""
    override = os.environ.get(CACHE_DIR_ENV)
    if override:
        return Path(override)
    return Path.home() / ".cache" / "solar-mcp"


def debug_enabled() -> bool:
    return os.environ.get(DEBUG_ENV) == "1"


def api_key_for(config: SourceConfig) -> str | None:
    key = os.environ.get(config.api_key_env)
    return key if key else None
