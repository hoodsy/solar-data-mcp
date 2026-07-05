"""lookup_tariffs: retail rate schedules serving a point or utility (URDB)."""

from typing import Any

from solar_mcp_core import units
from solar_mcp_core.envelope import ToolResult
from solar_mcp_core.errors import BadInput, SourceUnavailable
from solar_mcp_core.http import SolarHttpClient, freshness_warnings, source_ref
from solar_mcp_core.validation import validate_lat_lon

from solar_mcp_economics import api
from solar_mcp_economics.models import (
    DEFAULT_SECTOR,
    URDB_SECTOR,
    Tariff,
    normalize_tariff,
    validate_sector,
)

RESULT_LIMIT = 20


def _validate_location(lat: float | None, lon: float | None, utility_name: str | None) -> None:
    by_point = lat is not None and lon is not None
    if by_point == (utility_name is not None):
        raise BadInput(
            field="lat/lon | utility_name",
            value=f"lat={lat}, lon={lon}, utility_name={utility_name!r}",
            allowed="exactly one of: (lat AND lon) or utility_name",
        )
    if by_point:
        assert lat is not None and lon is not None
        validate_lat_lon(lat, lon)


async def lookup_tariffs(
    client: SolarHttpClient,
    *,
    lat: float | None = None,
    lon: float | None = None,
    utility_name: str | None = None,
    sector: str | None = None,
) -> ToolResult:
    _validate_location(lat, lon, utility_name)
    assumptions: list[str] = []
    if sector is None:
        sector = DEFAULT_SECTOR
        assumptions.append(f"sector not provided; defaulted to {DEFAULT_SECTOR}")
    sector = validate_sector(sector)

    result = await api.urdb_rates(
        client,
        lat=lat,
        lon=lon,
        utility_name=utility_name,
        sector_urdb=URDB_SECTOR[sector],
        limit=RESULT_LIMIT,
    )

    tariffs: list[Tariff] = []
    for item in result.response.items:
        tariff = normalize_tariff(item)
        if tariff is None:
            continue
        # utility_name filtering upstream is fuzzy; enforce the match here
        if utility_name is not None and utility_name.lower() not in tariff.utility.lower():
            continue
        tariffs.append(tariff)

    if not tariffs:
        where = f"({lat}, {lon})" if utility_name is None else repr(utility_name)
        raise SourceUnavailable(
            client.config.name,
            f"no approved {sector} rate schedules with energy rates found for {where}",
        )

    warnings = list(dict.fromkeys(note for t in tariffs for note in t.notes))
    warnings.extend(freshness_warnings(result.fetched))
    assumptions.append(
        f"approved schedules only; up to {RESULT_LIMIT} returned in URDB order — may "
        "include superseded filings (check startdate/enddate via each uri)"
    )

    data: dict[str, Any] = {
        "utilities": sorted({t.utility for t in tariffs}),
        "tariffs": [
            {
                "utility": t.utility,
                "name": t.name,
                "is_tou": t.is_tou,
                "is_seasonal": t.is_seasonal,
                "first_tier_rate_usd_per_kwh": t.first_tier_rate,
                "energy_tiers": [tier.model_dump() for tier in t.energy_tiers],
                "fixed_monthly_charge_usd": t.fixed_monthly_charge_usd,
                "uri": t.uri,
                "source": t.source,
            }
            for t in tariffs
        ],
    }
    return ToolResult(
        data=data,
        units={
            "utilities": units.LABEL,
            "tariffs[].first_tier_rate_usd_per_kwh": units.USD_PER_KWH,
            "tariffs[].energy_tiers[].rate_usd_per_kwh": units.USD_PER_KWH,
            "tariffs[].energy_tiers[].max_usage_kwh": units.KWH,
            "tariffs[].fixed_monthly_charge_usd": units.USD_PER_MONTH,
        },
        source=source_ref(
            "OpenEI Utility Rate Database v8", result.fetched, client.config.license_note
        ),
        assumptions=assumptions,
        warnings=warnings,
    )
