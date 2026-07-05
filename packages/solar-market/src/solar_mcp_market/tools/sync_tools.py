"""sync_tracking_the_sun / sync_solartrace: explicit bulk loaders (the only writers)."""

from solar_mcp_core.bulk import (
    SOLARTRACE_DATASET,
    TTS_DATASET,
    BulkStore,
    default_vintage,
    sync_result,
)
from solar_mcp_core.config import SOLARTRACE, TRACKING_THE_SUN
from solar_mcp_core.envelope import ToolResult
from solar_mcp_core.validation import validate_state

from solar_mcp_market.sync import load_solartrace, load_tracking_the_sun


async def sync_tracking_the_sun(
    store: BulkStore, *, source: str, vintage: str | None = None, state: str | None = None
) -> ToolResult:
    vintage, assumptions = default_vintage(vintage)
    if state is not None:
        state = validate_state(state)

    count = await load_tracking_the_sun(store, source=source, vintage=vintage, state=state)
    return sync_result(
        dataset=TTS_DATASET,
        rows_loaded=count,
        vintage=vintage,
        source_name="LBNL Tracking the Sun",
        source_url=source,
        license_note=TRACKING_THE_SUN.license_note,
        assumptions=assumptions,
        extra_data={"state_filter": state},
    )


async def sync_solartrace(
    store: BulkStore, *, source: str, vintage: str | None = None
) -> ToolResult:
    vintage, assumptions = default_vintage(vintage)
    count = await load_solartrace(store, source=source, vintage=vintage)
    return sync_result(
        dataset=SOLARTRACE_DATASET,
        rows_loaded=count,
        vintage=vintage,
        source_name="NREL SolarTRACE",
        source_url=source,
        license_note=SOLARTRACE.license_note,
        assumptions=assumptions,
    )
