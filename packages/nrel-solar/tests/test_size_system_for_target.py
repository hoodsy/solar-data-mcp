from collections.abc import Callable

import pytest
from helpers import assert_envelope
from solar_mcp_core.errors import BadInput
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_nrel.tools.size_system_for_target import MAX_CALLS, MAX_KW, MIN_KW, solve


class CountingProduction:
    def __init__(self, fn: Callable[[float], float]) -> None:
        self.fn = fn
        self.calls: list[float] = []

    async def __call__(self, kw: float) -> float:
        self.calls.append(kw)
        return float(self.fn(kw))


@pytest.mark.anyio
async def test_linear_production_converges_in_two_calls() -> None:
    production = CountingProduction(lambda kw: kw * 1000)
    result = await solve(5000, production)
    assert result.calls_used == 2
    assert result.required_kw == pytest.approx(5.0)
    assert result.pct_error == pytest.approx(0.0)
    assert not result.clamped


@pytest.mark.anyio
async def test_nonlinear_production_stays_within_call_cap() -> None:
    # Clipping-style nonlinearity the linear seed can't predict.
    production = CountingProduction(lambda kw: 1000 * kw - 30 * kw**2)
    result = await solve(6000, production)
    assert result.calls_used <= MAX_CALLS
    assert result.achieved_annual_kwh == pytest.approx(
        1000 * result.required_kw - 30 * result.required_kw**2
    )


@pytest.mark.anyio
async def test_tiny_target_clamps_to_min() -> None:
    production = CountingProduction(lambda kw: kw * 1000)
    result = await solve(10, production)  # seed 0.01 kW < MIN_KW
    assert result.clamped
    assert result.required_kw == MIN_KW


@pytest.mark.anyio
async def test_huge_target_clamps_to_max() -> None:
    production = CountingProduction(lambda kw: kw * 1000)
    result = await solve(1e12, production)  # seed 1e9 kW > MAX_KW
    assert result.clamped
    assert result.required_kw == MAX_KW
    assert result.pct_error < 0  # boundary system falls short of target


@pytest.mark.anyio
async def test_size_system_replay(nrel_client: SolarHttpClient) -> None:
    from solar_mcp_nrel.tools.size_system_for_target import size_system_for_target

    result = await size_system_for_target(
        nrel_client,
        lat=39.74,
        lon=-105.18,
        target_annual_kwh=6000,
        tilt_deg=25.0,
    )
    assert_envelope(result)
    assert 0.05 <= result.data["required_kw"] <= 500_000
    assert result.data["achieved_annual_kwh"] == pytest.approx(6000, rel=0.02)
    assert result.data["pvwatts_calls_used"] == 2  # linear seed converges immediately
    assert any("PVWatts calls" in a for a in result.assumptions)


@pytest.mark.anyio
async def test_size_system_rejects_nonpositive_target(nrel_client: SolarHttpClient) -> None:
    from solar_mcp_nrel.tools.size_system_for_target import size_system_for_target

    with pytest.raises(BadInput, match="target_annual_kwh"):
        await size_system_for_target(nrel_client, lat=39.74, lon=-105.18, target_annual_kwh=0)
