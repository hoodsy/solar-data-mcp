"""get_electricity_prices: state average retail prices with a 12-month trend (EIA)."""

from typing import Any

from solar_mcp_core import units
from solar_mcp_core.envelope import ToolResult
from solar_mcp_core.errors import BadInput, SourceUnavailable
from solar_mcp_core.http import SolarHttpClient, freshness_warnings, source_ref

from solar_mcp_economics import api
from solar_mcp_economics.models import EIA_SECTOR, validate_sector, validate_state

EIA_LICENSE = "U.S. Energy Information Administration (public domain)"
MAX_MONTHS = 60


async def get_electricity_prices(
    client: SolarHttpClient,
    *,
    state: str,
    sector: str | None = None,
    months: int | None = None,
) -> ToolResult:
    assumptions: list[str] = []
    state = validate_state(state)
    if sector is None:
        sector = "residential"
        assumptions.append("sector not provided; defaulted to residential")
    sector = validate_sector(sector)
    if months is None:
        months = 12
        assumptions.append("months not provided; defaulted to a 12-month trend")
    if not 1 <= months <= MAX_MONTHS:
        raise BadInput(field="months", value=months, allowed=f"1 to {MAX_MONTHS}")

    result = await api.eia_retail_prices(
        client, state=state, sector_eia=EIA_SECTOR[sector], months=months
    )
    points = result.response.response.data
    if not points:
        raise SourceUnavailable(client.config.name, f"no retail price data for {state}/{sector}")

    trend = sorted(
        ({"period": p.period, "price_cents_per_kwh": p.price_cents_per_kwh} for p in points),
        key=lambda row: str(row["period"]),
    )
    prices = [p.price_cents_per_kwh for p in points]
    latest = trend[-1]

    data: dict[str, Any] = {
        "state": state,
        "sector": sector,
        "latest_period": latest["period"],
        "latest_price_cents_per_kwh": latest["price_cents_per_kwh"],
        "average_cents_per_kwh": round(sum(prices) / len(prices), 2),
        "trend": trend,
    }
    return ToolResult(
        data=data,
        units={
            "state": units.LABEL,
            "sector": units.LABEL,
            "latest_period": units.ISO_DATE,
            "latest_price_cents_per_kwh": units.CENTS_PER_KWH,
            "average_cents_per_kwh": units.CENTS_PER_KWH,
            "trend[].price_cents_per_kwh": units.CENTS_PER_KWH,
        },
        source=source_ref("EIA API v2 electricity/retail-sales", result.fetched, EIA_LICENSE),
        assumptions=[
            *assumptions,
            f"average is over the {len(prices)} most recent months returned",
        ],
        warnings=freshness_warnings(result.fetched),
    )
