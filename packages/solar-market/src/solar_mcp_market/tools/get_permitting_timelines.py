"""get_permitting_timelines: SolarTRACE medians by jurisdiction or state."""

from typing import Any

from solar_mcp_core import units
from solar_mcp_core.bulk import SOLARTRACE_DATASET, SOLARTRACE_TABLE, BulkStore
from solar_mcp_core.config import SOLARTRACE
from solar_mcp_core.envelope import SourceRef, ToolResult
from solar_mcp_core.errors import BadInput, SourceUnavailable
from solar_mcp_core.validation import validate_state

SYNC_HINT = "run sync_solartrace(source=...) first"


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
        escaped = jurisdiction.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where, params = "WHERE lower(jurisdiction) LIKE ? ESCAPE '\\'", [f"%{escaped}%"]
    else:
        assert state is not None  # guaranteed by the exactly-one check above
        where, params = "WHERE upper(state) = ?", [state]

    # Medians over EVERY matching row; the jurisdiction list below is capped.
    summary = store.query(
        f"SELECT count(*), median(median_permit_days), median(median_inspection_days), "
        f"median(median_pto_days) FROM {SOLARTRACE_TABLE} {where}",
        params,
    )[0]
    total_matches = int(summary[0])
    if total_matches == 0:
        target = jurisdiction if jurisdiction is not None else state
        raise SourceUnavailable(
            SOLARTRACE.name, f"no SolarTRACE rows match {target!r} in the synced snapshot"
        )

    rows = store.query(
        f"SELECT jurisdiction, upper(state), median_permit_days, "
        f"median_inspection_days, median_pto_days FROM {SOLARTRACE_TABLE} {where} "
        "ORDER BY jurisdiction LIMIT 50",
        params,
    )
    jurisdictions: list[dict[str, Any]] = [
        {
            "jurisdiction": str(j),
            "state": str(s),
            "median_permit_days": float(perm) if perm is not None else None,
            "median_inspection_days": float(insp) if insp is not None else None,
            "median_pto_days": float(pto) if pto is not None else None,
        }
        for j, s, perm, insp, pto in rows
    ]
    warnings: list[str] = []
    if total_matches > len(jurisdictions):
        warnings.append(
            f"listing {len(jurisdictions)} of {total_matches} matching jurisdictions; "
            "the top-level medians cover all matches"
        )

    vintage = store.vintage(SOLARTRACE_DATASET)
    return ToolResult(
        data={
            "jurisdictions": jurisdictions,
            "jurisdictions_matched": total_matches,
            "median_permit_days": float(summary[1]) if summary[1] is not None else None,
            "median_inspection_days": float(summary[2]) if summary[2] is not None else None,
            "median_pto_days": float(summary[3]) if summary[3] is not None else None,
        },
        units={
            "jurisdictions[].jurisdiction": units.LABEL,
            "jurisdictions[].state": units.LABEL,
            "jurisdictions[].median_permit_days": units.DAYS,
            "jurisdictions[].median_inspection_days": units.DAYS,
            "jurisdictions[].median_pto_days": units.DAYS,
            "jurisdictions_matched": units.COUNT,
            "median_permit_days": units.DAYS,
            "median_inspection_days": units.DAYS,
            "median_pto_days": units.DAYS,
        },
        source=SourceRef(
            name="NREL SolarTRACE (local snapshot)",
            url="https://maps.nlr.gov/solarTRACE/",
            retrieved_at=vintage.loaded_at if vintage else "unknown",
            license=SOLARTRACE.license_note,
        ),
        assumptions=[
            f"snapshot vintage {vintage.vintage if vintage else 'unknown'}",
            "top-level medians are computed across every matching jurisdiction row",
        ],
        warnings=warnings,
    )
