"""Per-source configuration registry.

Each data source gets one SourceConfig describing where it lives, how it
authenticates, how hard we may hit it, and how long responses stay fresh.
The registry lives in core so `solar-mcp doctor` can iterate every known
source without importing server packages.
"""

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

CACHE_DIR_ENV = "SOLAR_MCP_CACHE_DIR"
DEBUG_ENV = "SOLAR_MCP_DEBUG"

AuthStyle = Literal["api_key_param", "token_header", "none"]


class SourceConfig(BaseModel):
    name: str
    base_url: str
    rate_limit_per_hour: int
    cache_ttl_seconds: int
    license_note: str
    docs_url: str
    # None means the source is unauthenticated (public bulk data / open REST).
    api_key_env: str | None = None
    auth_style: AuthStyle = "api_key_param"
    # Optional sources (e.g. email-issued tokens) SKIP rather than FAIL in doctor.
    required: bool = True
    signup_url: str | None = None
    # Cheapest keyed endpoint, used by `solar-mcp doctor` as the liveness ping.
    ping_path: str | None = None
    ping_params: dict[str, str | int | float] = Field(default_factory=dict)


NREL = SourceConfig(
    name="nrel",
    base_url="https://developer.nlr.gov",
    api_key_env="NREL_API_KEY",
    rate_limit_per_hour=1000,
    cache_ttl_seconds=30 * 86400,  # TMY results are deterministic per location+params
    license_note="NREL Developer Network — free API, attribution appreciated",
    docs_url="https://developer.nlr.gov/docs/solar/",
    signup_url="https://developer.nlr.gov/signup/",
    ping_path="/api/solar/solar_resource/v1.json",
    ping_params={"lat": 39.74, "lon": -105.18},
)

OPENEI = SourceConfig(
    name="openei",
    base_url="https://api.openei.org",
    api_key_env="OPENEI_API_KEY",
    rate_limit_per_hour=1000,
    cache_ttl_seconds=7 * 86400,  # tariffs change on filing cycles, not daily
    license_note="OpenEI Utility Rate Database — free API; data CC-BY",
    docs_url="https://openei.org/services/doc/rest/util_rates/",
    signup_url="https://openei.org/services/api/signup/",
    ping_path="/utility_rates",
    ping_params={"version": 8, "format": "json", "lat": 39.74, "lon": -105.18, "limit": 1},
)

EIA = SourceConfig(
    name="eia",
    base_url="https://api.eia.gov",
    api_key_env="EIA_API_KEY",
    rate_limit_per_hour=5000,
    cache_ttl_seconds=7 * 86400,
    license_note="U.S. Energy Information Administration — public domain",
    docs_url="https://www.eia.gov/opendata/documentation.php",
    signup_url="https://www.eia.gov/opendata/register.php",
    ping_path="/v2/electricity/retail-sales/data/",
    ping_params={"frequency": "annual", "data[0]": "price", "length": 1},
)

DSIRE = SourceConfig(
    name="dsire",
    base_url="https://programs.dsireusa.org",
    auth_style="none",
    rate_limit_per_hour=60,
    cache_ttl_seconds=7 * 86400,
    license_note="DSIRE (NC Clean Energy Technology Center) — public bulk snapshots",
    docs_url="https://dsireusa.org/dsire-api/",
    # Bulk-download source: refreshed via sync_incentives, no cheap liveness ping.
)

USPVDB = SourceConfig(
    name="uspvdb",
    base_url="https://energy.usgs.gov",
    auth_style="none",
    rate_limit_per_hour=600,
    cache_ttl_seconds=30 * 86400,  # facility data updates quarterly
    license_note="USGS/LBNL US Large-Scale Solar Photovoltaic Database — public domain",
    docs_url="https://energy.usgs.gov/uspvdb/api-doc/",
    ping_path="/api/uspvdb/v1/projects",
    ping_params={"limit": 1},
)

AHJ = SourceConfig(
    name="ahj",
    base_url="https://ahjregistry.sunspec.org",
    api_key_env="AHJ_REGISTRY_TOKEN",
    auth_style="token_header",
    required=False,  # token is issued by email from support@sunspec.org
    rate_limit_per_hour=100,  # registry access is throttled
    cache_ttl_seconds=90 * 86400,  # AHJ boundaries change rarely
    license_note="SunSpec AHJ Registry — token access, throttled",
    docs_url="https://sunspec.org/ahj-registry/",
    signup_url="mailto:support@sunspec.org",
)

TRACKING_THE_SUN = SourceConfig(
    name="tts",
    base_url="https://emp.lbl.gov",
    auth_style="none",
    rate_limit_per_hour=10,
    cache_ttl_seconds=0,  # bulk downloads only, via sync_tracking_the_sun
    license_note="LBNL Tracking the Sun — public data files, cached locally, never re-hosted",
    docs_url="https://emp.lbl.gov/tracking-the-sun",
)

SOLARTRACE = SourceConfig(
    name="solartrace",
    base_url="https://maps.nlr.gov",
    auth_style="none",
    rate_limit_per_hour=10,
    cache_ttl_seconds=0,  # bulk downloads only, via sync_solartrace
    license_note="NREL SolarTRACE — public dataset, cached locally",
    docs_url="https://maps.nlr.gov/solarTRACE/",
)

SOURCES: dict[str, SourceConfig] = {
    config.name: config
    for config in (NREL, OPENEI, EIA, DSIRE, USPVDB, AHJ, TRACKING_THE_SUN, SOLARTRACE)
}


def cache_dir() -> Path:
    """Cache directory: $SOLAR_MCP_CACHE_DIR or ~/.cache/solar-mcp."""
    override = os.environ.get(CACHE_DIR_ENV)
    if override:
        return Path(override)
    return Path.home() / ".cache" / "solar-mcp"


def debug_enabled() -> bool:
    return os.environ.get(DEBUG_ENV) == "1"


def api_key_for(config: SourceConfig) -> str | None:
    if config.api_key_env is None:
        return None
    key = os.environ.get(config.api_key_env)
    return key if key else None
