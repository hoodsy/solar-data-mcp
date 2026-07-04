"""size_system_for_target: inverse-solve annual kWh target to required kW."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from solar_mcp_core import units
from solar_mcp_core.envelope import ToolResult
from solar_mcp_core.errors import BadInput, SolarMCPError
from solar_mcp_core.http import SolarHttpClient

from solar_mcp_nrel.models import SystemSpec
from solar_mcp_nrel.tools.estimate_production import estimate_production

MIN_KW = 0.05
MAX_KW = 500_000.0
TOLERANCE = 0.02
MAX_CALLS = 6
_PROBE_KW = 4.0

ProductionFn = Callable[[float], Awaitable[float]]


@dataclass
class SolveResult:
    required_kw: float
    achieved_annual_kwh: float
    pct_error: float
    calls_used: int
    clamped: bool


async def solve(target_kwh: float, production: ProductionFn) -> SolveResult:
    """Find the capacity whose annual production hits the target within 2%.

    PVWatts output is close to linear in system_capacity at fixed dc_ac_ratio,
    so one probe call yields the specific yield and a near-exact seed; a
    bisection fallback (capped at MAX_CALLS total, bracket clamped to PVWatts'
    legal capacity range) covers any nonlinearity. Pure with respect to HTTP:
    the production callable is the seam.
    """
    calls = 0

    async def produce(kw: float) -> float:
        nonlocal calls
        calls += 1
        return await production(kw)

    probe_ac = await produce(_PROBE_KW)
    if probe_ac <= 0:
        raise SolarMCPError(
            f"cannot size a system here: a {_PROBE_KW} kW probe produced "
            f"{probe_ac} kWh/yr, so no capacity can reach the target"
        )
    specific_yield = probe_ac / _PROBE_KW  # kWh per kW per year
    seed_kw = target_kwh / specific_yield

    if seed_kw < MIN_KW or seed_kw > MAX_KW:
        clamped_kw = min(max(seed_kw, MIN_KW), MAX_KW)
        achieved = await produce(clamped_kw)
        error = (achieved - target_kwh) / target_kwh
        return SolveResult(clamped_kw, achieved, round(error * 100, 2), calls, clamped=True)

    best_kw, best_ac = seed_kw, await produce(seed_kw)
    lo, hi = max(seed_kw / 2, MIN_KW), min(seed_kw * 2, MAX_KW)
    while abs(best_ac - target_kwh) / target_kwh > TOLERANCE and calls < MAX_CALLS:
        if best_ac < target_kwh:
            lo = best_kw
        else:
            hi = best_kw
        best_kw = (lo + hi) / 2
        best_ac = await produce(best_kw)

    error = (best_ac - target_kwh) / target_kwh
    return SolveResult(best_kw, best_ac, round(error * 100, 2), calls, clamped=False)


async def size_system_for_target(
    client: SolarHttpClient,
    spec: SystemSpec,
    target_annual_kwh: float,
) -> ToolResult:
    if target_annual_kwh <= 0:
        raise BadInput(field="target_annual_kwh", value=target_annual_kwh, allowed="> 0")

    async def estimate(kw: float) -> ToolResult:
        return await estimate_production(client, spec, round(kw, 3))

    async def production(kw: float) -> float:
        result = await estimate(kw)
        return float(result.data["ac_annual_kwh"])

    solved = await solve(target_annual_kwh, production)
    # The solver's last probe used exactly this capacity, so this is a cache
    # hit — no extra API call — and the envelope describes the solved system.
    final = await estimate(solved.required_kw)

    warnings = [*final.warnings]
    if solved.clamped:
        bound = "minimum" if solved.required_kw == MIN_KW else "maximum"
        warnings.insert(
            0,
            f"target {target_annual_kwh} kWh/yr is outside PVWatts' {bound} system "
            f"size ({solved.required_kw} kW); returning the boundary system instead",
        )
    elif abs(solved.pct_error) > TOLERANCE * 100:
        warnings.insert(
            0,
            f"solver stopped at {solved.pct_error:+.1f}% from target after "
            f"{solved.calls_used} PVWatts calls",
        )

    return ToolResult(
        data={
            "required_kw": round(solved.required_kw, 3),
            "achieved_annual_kwh": solved.achieved_annual_kwh,
            "pct_error": solved.pct_error,
            "pvwatts_calls_used": solved.calls_used,
        },
        units={
            "required_kw": units.KW_DC,
            "achieved_annual_kwh": units.KWH_AC_PER_YEAR,
            "pct_error": units.PERCENT,
            "pvwatts_calls_used": units.COUNT,
        },
        source=final.source,
        assumptions=[
            f"solved to within {TOLERANCE:.0%} of target using at most {MAX_CALLS} "
            "PVWatts calls (production is ~linear in capacity)",
            *final.assumptions,
        ],
        warnings=warnings,
    )
