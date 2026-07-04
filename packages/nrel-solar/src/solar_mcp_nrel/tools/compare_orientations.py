"""compare_orientations: tilt x azimuth sweep, ranked against the optimum."""

import asyncio
from typing import Any

from solar_mcp_core import units
from solar_mcp_core.envelope import ToolResult
from solar_mcp_core.errors import BadInput, SolarMCPError
from solar_mcp_core.http import SolarHttpClient

from solar_mcp_nrel.tools._envelope import PVWATTS_CAVEAT
from solar_mcp_nrel.tools.estimate_production import estimate_production

MAX_COMBINATIONS = 25  # hard bound on PVWatts calls per sweep
DEFAULT_TILTS = [0.0, 10.0, 20.0, 30.0, 40.0]
DEFAULT_AZIMUTHS = [90.0, 135.0, 180.0, 225.0, 270.0]
_CONCURRENCY = 4


def rank_grid(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort by production descending and add % delta vs the best cell. Pure."""
    ranked = sorted(cells, key=lambda c: float(c["ac_annual_kwh"]), reverse=True)
    if not ranked:
        return ranked
    best = float(ranked[0]["ac_annual_kwh"])
    for cell in ranked:
        delta = 0.0 if best == 0 else (float(cell["ac_annual_kwh"]) - best) / best * 100
        cell["pct_delta_vs_best"] = round(delta, 2)
    return ranked


def validate_grid(tilts: list[float], azimuths: list[float]) -> None:
    """Bound the sweep before any HTTP happens. Pure."""
    if not tilts or not azimuths:
        raise BadInput(
            field="tilts/azimuths",
            value=f"{len(tilts)}x{len(azimuths)}",
            allowed="at least one value each",
        )
    if len(tilts) * len(azimuths) > MAX_COMBINATIONS:
        raise BadInput(
            field="tilts x azimuths",
            value=f"{len(tilts)}x{len(azimuths)}={len(tilts) * len(azimuths)}",
            allowed=f"<= {MAX_COMBINATIONS} combinations per sweep",
        )


async def compare_orientations(
    client: SolarHttpClient,
    *,
    lat: float,
    lon: float,
    system_capacity_kw: float,
    tilts: list[float] | None = None,
    azimuths: list[float] | None = None,
    array_type: str = "fixed_roof",
    module_type: str = "standard",
    losses_pct: float = 14.0,
    dc_ac_ratio: float = 1.2,
) -> ToolResult:
    assumptions: list[str] = []
    if tilts is None:
        tilts = list(DEFAULT_TILTS)
        assumptions.append(f"tilts not provided; swept default grid {tilts}")
    if azimuths is None:
        azimuths = list(DEFAULT_AZIMUTHS)
        assumptions.append(
            f"azimuths not provided; swept default grid {azimuths} (90=E, 180=S, 270=W)"
        )
    validate_grid(tilts, azimuths)

    semaphore = asyncio.Semaphore(_CONCURRENCY)
    warnings: list[str] = []
    source = None

    async def run_cell(tilt: float, azimuth: float) -> dict[str, Any] | None:
        nonlocal source
        async with semaphore:
            try:
                result = await estimate_production(
                    client,
                    lat=lat,
                    lon=lon,
                    system_capacity_kw=system_capacity_kw,
                    tilt_deg=tilt,
                    azimuth_deg=azimuth,
                    array_type=array_type,
                    module_type=module_type,
                    losses_pct=losses_pct,
                    dc_ac_ratio=dc_ac_ratio,
                )
            except SolarMCPError as exc:
                warnings.append(f"tilt={tilt}, azimuth={azimuth} failed: {exc}")
                return None
            source = result.source
            return {
                "tilt": tilt,
                "azimuth": azimuth,
                "ac_annual_kwh": result.data["ac_annual_kwh"],
            }

    cells = await asyncio.gather(*(run_cell(t, a) for t in tilts for a in azimuths))
    completed = [c for c in cells if c is not None]
    if not completed or source is None:
        raise SolarMCPError(
            f"all {len(tilts) * len(azimuths)} orientation combinations failed; "
            f"first failure: {warnings[0] if warnings else 'unknown'}"
        )
    failed = len(cells) - len(completed)
    if failed:
        warnings.insert(0, f"partial result: {failed}/{len(cells)} combinations failed")

    ranked = rank_grid(completed)
    return ToolResult(
        data={
            "ranked": ranked,
            "best": {"tilt": ranked[0]["tilt"], "azimuth": ranked[0]["azimuth"]},
        },
        units={
            "ranked": f"per cell: tilt {units.DEGREES}, azimuth {units.DEGREES}, "
            f"ac_annual_kwh {units.KWH_AC_PER_YEAR}, pct_delta_vs_best {units.PERCENT}",
            "best": units.DEGREES,
        },
        source=source,
        assumptions=[
            *assumptions,
            f"losses_pct={losses_pct}, array_type={array_type}, "
            f"module_type={module_type}, dc_ac_ratio={dc_ac_ratio} applied to every cell",
        ],
        warnings=[*warnings, PVWATTS_CAVEAT],
    )
