from collections.abc import Callable

import pytest
from solar_mcp_core.config import EIA, SourceConfig
from solar_mcp_core.errors import BadInput
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_economics.tools.get_electricity_prices import get_electricity_prices

from conftest import assert_envelope

ClientFor = Callable[[SourceConfig], SolarHttpClient]


@pytest.mark.anyio
async def test_colorado_prices_replay(client_for: ClientFor) -> None:
    result = await get_electricity_prices(client_for(EIA), state="CO")
    assert_envelope(result)
    assert 5 < result.data["latest_price_cents_per_kwh"] < 60  # sane US retail range
    assert 5 < result.data["average_cents_per_kwh"] < 60
    trend = result.data["trend"]
    assert len(trend) == 12
    periods = [row["period"] for row in trend]
    assert periods == sorted(periods), "trend must be chronological"
    assert result.data["latest_period"] == periods[-1]
    assert any("12-month" in a for a in result.assumptions)


@pytest.mark.anyio
async def test_invalid_inputs_rejected_before_http(client_for: ClientFor) -> None:
    client = client_for(EIA)
    with pytest.raises(BadInput, match="state"):
        await get_electricity_prices(client, state="ZZ")
    with pytest.raises(BadInput, match="months"):
        await get_electricity_prices(client, state="CO", months=0)
