"""query_installed_systems: aggregate stats from the Tracking the Sun snapshot."""

from typing import Any

from solar_mcp_core import units
from solar_mcp_core.bulk import TTS_DATASET, TTS_TABLE, BulkStore
from solar_mcp_core.config import TRACKING_THE_SUN
from solar_mcp_core.envelope import SourceRef, ToolResult
from solar_mcp_core.errors import BadInput, SourceUnavailable
from solar_mcp_core.validation import validate_state

SYNC_HINT = "run sync_tracking_the_sun(source=...) first"


async def query_installed_systems(
    store: BulkStore,
    *,
    state: str,
    year_start: int | None = None,
    year_end: int | None = None,
) -> ToolResult:
    state = validate_state(state)
    if year_start is not None and year_end is not None and year_start > year_end:
        raise BadInput(
            field="year_start/year_end",
            value=f"{year_start}..{year_end}",
            allowed="year_start <= year_end",
        )
    if not store.has_table(TTS_TABLE):
        raise SourceUnavailable(
            TRACKING_THE_SUN.name, f"Tracking the Sun snapshot not synced; {SYNC_HINT}"
        )

    where = "WHERE state = ?"
    params: list[Any] = [state]
    if year_start is not None:
        where += " AND year >= ?"
        params.append(year_start)
    if year_end is not None:
        where += " AND year <= ?"
        params.append(year_end)

    summary = store.query(
        f"SELECT count(*), median(price_per_watt), "
        f"quantile_cont(size_kw, 0.25), median(size_kw), quantile_cont(size_kw, 0.75) "
        f"FROM {TTS_TABLE} {where}",
        params,
    )[0]
    count = int(summary[0])
    if count == 0:
        raise SourceUnavailable(
            TRACKING_THE_SUN.name,
            f"no Tracking the Sun records for {state} in the synced snapshot "
            "(try a different state or a wider year range)",
        )

    top_modules = store.query(
        f"SELECT module_manufacturer, count(*) AS n FROM {TTS_TABLE} {where} "
        "AND module_manufacturer IS NOT NULL GROUP BY 1 ORDER BY n DESC LIMIT 3",
        params,
    )

    vintage = store.vintage(TTS_DATASET)
    data: dict[str, Any] = {
        "state": state,
        "system_count": count,
        "median_price_per_watt": round(float(summary[1]), 2) if summary[1] is not None else None,
        "size_kw_p25": round(float(summary[2]), 2) if summary[2] is not None else None,
        "size_kw_median": round(float(summary[3]), 2) if summary[3] is not None else None,
        "size_kw_p75": round(float(summary[4]), 2) if summary[4] is not None else None,
        "top_modules": [{"manufacturer": str(m), "count": int(n)} for m, n in top_modules],
    }
    return ToolResult(
        data=data,
        units={
            "state": units.LABEL,
            "system_count": units.COUNT,
            "median_price_per_watt": units.USD_PER_WATT,
            "size_kw_p25": units.KW_DC,
            "size_kw_median": units.KW_DC,
            "size_kw_p75": units.KW_DC,
            "top_modules[].manufacturer": units.LABEL,
            "top_modules[].count": units.COUNT,
        },
        source=SourceRef(
            name="LBNL Tracking the Sun (local snapshot)",
            url="https://emp.lbl.gov/tracking-the-sun",
            retrieved_at=vintage.loaded_at if vintage else "unknown",
            license=TRACKING_THE_SUN.license_note,
        ),
        assumptions=[
            f"snapshot vintage {vintage.vintage if vintage else 'unknown'}",
            "aggregate statistics only — row-level records are never returned",
        ],
        warnings=[],
    )
