"""Typed calls to the URDB and EIA endpoints this server wraps."""

from dataclasses import dataclass
from typing import Any

from solar_mcp_core.http import FetchedResponse, SolarHttpClient

from solar_mcp_economics.models import EiaResponse, UrdbResponse

URDB_PATH = "/utility_rates"
EIA_RETAIL_PATH = "/v2/electricity/retail-sales/data/"


@dataclass
class UrdbResult:
    response: UrdbResponse
    fetched: FetchedResponse


@dataclass
class EiaResult:
    response: EiaResponse
    fetched: FetchedResponse


async def urdb_rates(
    client: SolarHttpClient,
    *,
    lat: float | None = None,
    lon: float | None = None,
    utility_name: str | None = None,
    sector_urdb: str,
    limit: int = 20,
) -> UrdbResult:
    params: dict[str, Any] = {
        "version": 8,
        "format": "json",
        "detail": "full",
        "approved": "true",
        "sector": sector_urdb,
        "limit": limit,
    }
    if lat is not None and lon is not None:
        params["lat"] = lat
        params["lon"] = lon
    if utility_name is not None:
        params["utility_name"] = utility_name
    fetched = await client.get_json(URDB_PATH, params)
    return UrdbResult(UrdbResponse.model_validate(fetched.data), fetched)


async def eia_retail_prices(
    client: SolarHttpClient,
    *,
    state: str,
    sector_eia: str,
    months: int = 12,
) -> EiaResult:
    params: dict[str, Any] = {
        "frequency": "monthly",
        "data[0]": "price",
        "facets[stateid][]": state,
        "facets[sectorid][]": sector_eia,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": months,
    }
    fetched = await client.get_json(EIA_RETAIL_PATH, params)
    return EiaResult(EiaResponse.model_validate(fetched.data), fetched)
