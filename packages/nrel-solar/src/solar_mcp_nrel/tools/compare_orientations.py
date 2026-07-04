"""compare_orientations: tilt x azimuth sweep, ranked against the optimum."""

import asyncio
from dataclasses import replace
from typing import Any

from solar_mcp_core import units
from solar_mcp_core.envelope import SourceRef, ToolResult
from solar_mcp_core.errors import BadInput, QuotaExceeded, SolarMCPError, SourceUnavailable
from solar_mcp_core.http import SolarHttpClient

from solar_mcp_nrel.models import SystemSpec
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
    """Bound the sweep and range-check every value before any HTTP happens. Pure."""
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
    for i, tilt in enumerate(tilts):
        if not 0 <= tilt <= 90:
            raise BadInput(field=f"tilts[{i}]", value=tilt, allowed="0 to 90 degrees")
    for i, azimuth in enumerate(azimuths):
        if not 0 <= azimuth < 360:
            raise BadInput(field=f"azimuths[{i}]", value=azimuth, allowed="0 to <360 degrees")


async def compare_orientations(
    client: SolarHttpClient,
    spec: SystemSpec,
    system_capacity_kw: float,
    tilts: list[float] | None = None,
    azimuths: list[float] | None = None,
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
    total = len(tilts) * len(azimuths)

    semaphore = asyncio.Semaphore(_CONCURRENCY)
    failures: list[str] = []
    skipped = 0
    quota_hit = False

    async def run_cell(tilt: float, azimuth: float) -> dict[str, Any] | None:
        nonlocal skipped, quota_hit
        async with semaphore:
            if quota_hit:
                skipped += 1  # don't burn an exhausted rolling window further
                return None
            cell_spec = replace(spec, tilt_deg=tilt, azimuth_deg=azimuth)
            try:
                result = await estimate_production(client, cell_spec, system_capacity_kw)
            except QuotaExceeded as exc:
                quota_hit = True
                failures.append(f"tilt_deg={tilt}, azimuth_deg={azimuth}: {exc}")
                return None
            except SolarMCPError as exc:
                failures.append(f"tilt_deg={tilt}, azimuth_deg={azimuth}: {exc}")
                return None
            return {
                "tilt_deg": tilt,
                "azimuth_deg": azimuth,
                "ac_annual_kwh": result.data["ac_annual_kwh"],
                "source": result.source,
                "warnings": result.warnings,
                "assumptions": result.assumptions,
            }

    cells = [
        c for c in await asyncio.gather(*(run_cell(t, a) for t in tilts for a in azimuths)) if c
    ]
    if not cells:
        raise SourceUnavailable(
            client.config.name,
            f"all {total} orientation combinations failed; first failure: "
            f"{failures[0] if failures else 'unknown'}",
        )

    warnings: list[str] = []
    if failures or skipped:
        note = f"partial result: {len(failures)} of {total} combinations failed"
        if skipped:
            note += f"; {skipped} not attempted after the rate limit was hit"
        warnings.append(note)
        warnings.extend(failures)
    # Per-cell warnings (stale cache, station distance, PVWatts caveat) and the
    # system defaults injected per cell — identical across cells, so deduped.
    warnings.extend(dict.fromkeys(w for cell in cells for w in cell["warnings"]))
    assumptions.extend(dict.fromkeys(a for cell in cells for a in cell["assumptions"]))

    ranked = rank_grid(
        [{k: cell[k] for k in ("tilt_deg", "azimuth_deg", "ac_annual_kwh")} for cell in cells]
    )
    best = ranked[0]
    best_source: SourceRef = next(
        cell["source"]
        for cell in cells
        if cell["tilt_deg"] == best["tilt_deg"] and cell["azimuth_deg"] == best["azimuth_deg"]
    )

    return ToolResult(
        data={
            "ranked": ranked,
            "best": {"tilt_deg": best["tilt_deg"], "azimuth_deg": best["azimuth_deg"]},
        },
        units={
            "ranked[].tilt_deg": units.DEGREES,
            "ranked[].azimuth_deg": units.DEGREES,
            "ranked[].ac_annual_kwh": units.KWH_AC_PER_YEAR,
            "ranked[].pct_delta_vs_best": units.PERCENT,
            "best.tilt_deg": units.DEGREES,
            "best.azimuth_deg": units.DEGREES,
        },
        source=best_source,
        assumptions=assumptions,
        warnings=warnings,
    )
