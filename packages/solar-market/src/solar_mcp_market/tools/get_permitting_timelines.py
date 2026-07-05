"""get_permitting_timelines: SolarTRACE medians by jurisdiction or state."""

from typing import Any

from solar_mcp_core import units
from solar_mcp_core.bulk import BulkStore
from solar_mcp_core.config import SOLARTRACE
from solar_mcp_core.envelope import SourceRef, ToolResult
from solar_mcp_core.errors import BadInput, SourceUnavailable

from solar_mcp_market.models import validate_state
from solar_mcp_market.sync import SOLARTRACE_DATASET, SOLARTRACE_TABLE

SYNC_HINT = "run sync_solartrace(source=...) first"
DAYS = "days"


async def get_permitting_timelines(
    store: BulkStore,
    *,
    state: str | None = None,
    jurisdiction: str | None = None,
) -> ToolResult:
    if (state is None) == (jurisdiction is None):
        raise BadInput(
            field="state | jurisdiction",
            value=f"state={state}, jurisdiction={jurisdiction}",
            allowed="exactly one of state or jurisdiction",
        )
    if state is not None:
        state = validate_state(state)
    if not store.has_table(SOLARTRACE_TABLE):
        raise SourceUnavailable(SOLARTRACE.name, f"SolarTRACE snapshot not synced; {SYNC_HINT}")

    if jurisdiction is not None:
        where, params = "WHERE lower(jurisdiction) LIKE ?", [f"%{jurisdiction.lower()}%"]
    else:
        assert state is not None  # guaranteed by the exactly-one check above
        where, params = "WHERE upper(state) = ?", [state]

    rows = store.query(
        f"SELECT jurisdiction, upper(state), median_permit_days, "
        f"median_inspection_days, median_pto_days FROM {SOLARTRACE_TABLE} {where} "
        "ORDER BY jurisdiction LIMIT 50",
        list(params),
    )
    if not rows:
        target = jurisdiction if jurisdiction is not None else state
        raise SourceUnavailable(
            SOLARTRACE.name, f"no SolarTRACE rows match {target!r} in the synced snapshot"
        )

    jurisdictions: list[dict[str, Any]] = [
        {
            "jurisdiction": str(j),
            "state": str(s),
            "median_permit_days": float(p) if p is not None else None,
            "median_inspection_days": float(i) if i is not None else None,
            "median_pto_days": float(pto) if pto is not None else None,
        }
        for j, s, p, i, pto in rows
    ]

    def _median_of(field: str) -> float | None:
        values = sorted(row[field] for row in jurisdictions if row[field] is not None)
        if not values:
            return None
        middle = len(values) // 2
        if len(values) % 2:
            return float(values[middle])
        return float((values[middle - 1] + values[middle]) / 2)

    vintage = store.vintage(SOLARTRACE_DATASET)
    return ToolResult(
        data={
            "jurisdictions": jurisdictions,
            "median_permit_days": _median_of("median_permit_days"),
            "median_inspection_days": _median_of("median_inspection_days"),
            "median_pto_days": _median_of("median_pto_days"),
        },
        units={
            "jurisdictions[].jurisdiction": units.LABEL,
            "jurisdictions[].state": units.LABEL,
            "jurisdictions[].median_permit_days": DAYS,
            "jurisdictions[].median_inspection_days": DAYS,
            "jurisdictions[].median_pto_days": DAYS,
            "median_permit_days": DAYS,
            "median_inspection_days": DAYS,
            "median_pto_days": DAYS,
        },
        source=SourceRef(
            name="NREL SolarTRACE (local snapshot)",
            url="https://maps.nlr.gov/solarTRACE/",
            retrieved_at=vintage.loaded_at if vintage else "unknown",
            license=SOLARTRACE.license_note,
        ),
        assumptions=[
            f"snapshot vintage {vintage.vintage if vintage else 'unknown'}",
            "top-level medians are medians of the matched jurisdictions' medians",
        ],
        warnings=[],
    )
