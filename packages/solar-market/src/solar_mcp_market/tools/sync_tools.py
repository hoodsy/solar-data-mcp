"""sync_tracking_the_sun / sync_solartrace: explicit bulk loaders (the only writers)."""

from datetime import UTC, datetime

from solar_mcp_core import units
from solar_mcp_core.bulk import BulkStore
from solar_mcp_core.config import SOLARTRACE, TRACKING_THE_SUN
from solar_mcp_core.envelope import SourceRef, ToolResult

from solar_mcp_market.models import validate_state
from solar_mcp_market.sync import (
    SOLARTRACE_DATASET,
    TTS_DATASET,
    load_solartrace,
    load_tracking_the_sun,
)

_SYNC_UNITS = {
    "dataset": units.LABEL,
    "rows_loaded": units.COUNT,
    "vintage": units.ISO_DATE,
    "state_filter": units.LABEL,
}


def _now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def sync_tracking_the_sun(
    store: BulkStore, *, source: str, vintage: str | None = None, state: str | None = None
) -> ToolResult:
    assumptions: list[str] = []
    if vintage is None:
        vintage = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        assumptions.append(f"vintage not provided; recorded as today ({vintage})")
    if state is not None:
        state = validate_state(state)

    count = await load_tracking_the_sun(store, source=source, vintage=vintage, state=state)
    return ToolResult(
        data={
            "dataset": TTS_DATASET,
            "rows_loaded": count,
            "vintage": vintage,
            "state_filter": state,
        },
        units=_SYNC_UNITS,
        source=SourceRef(
            name="LBNL Tracking the Sun",
            url=source,
            retrieved_at=_now_iso(),
            license=TRACKING_THE_SUN.license_note,
        ),
        assumptions=assumptions,
        warnings=[],
    )


async def sync_solartrace(
    store: BulkStore, *, source: str, vintage: str | None = None
) -> ToolResult:
    assumptions: list[str] = []
    if vintage is None:
        vintage = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        assumptions.append(f"vintage not provided; recorded as today ({vintage})")

    count = await load_solartrace(store, source=source, vintage=vintage)
    return ToolResult(
        data={"dataset": SOLARTRACE_DATASET, "rows_loaded": count, "vintage": vintage},
        units=_SYNC_UNITS,
        source=SourceRef(
            name="NREL SolarTRACE",
            url=source,
            retrieved_at=_now_iso(),
            license=SOLARTRACE.license_note,
        ),
        assumptions=assumptions,
        warnings=[],
    )
