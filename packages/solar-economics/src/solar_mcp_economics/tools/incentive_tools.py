"""get_incentives and sync_incentives: federal ITC table + DSIRE snapshots."""

import asyncio
from datetime import UTC, datetime

from solar_mcp_core import units
from solar_mcp_core.bulk import (
    DSIRE_DATASET,
    BulkStore,
    default_vintage,
    fetch_to_tempfile,
    sync_result,
)
from solar_mcp_core.config import DSIRE
from solar_mcp_core.envelope import SourceRef, ToolResult, utc_now_iso
from solar_mcp_core.errors import BadInput
from solar_mcp_core.localfile import resolve_local_data_file
from solar_mcp_core.validation import validate_state

from solar_mcp_economics.economics import ITC_CITATION
from solar_mcp_economics.incentives import (
    DSIRE_DOWNLOAD_HELP,
    federal_incentives,
    snapshot_vintage,
    state_programs,
    sync_snapshot,
)

_INCENTIVE_UNITS = {
    "state": units.LABEL,
    "snapshot_vintage": units.ISO_DATE,
    "federal[].name": units.LABEL,
    "federal[].value": units.LABEL,
    "federal[].expiry": units.ISO_DATE,
    "state_local[].name": units.LABEL,
    "state_local[].value": units.LABEL,
    "state_local[].expiry": units.ISO_DATE,
}


async def get_incentives(
    store: BulkStore, *, state: str, install_year: int | None = None
) -> ToolResult:
    assumptions = [f"federal table: {ITC_CITATION}"]
    state = validate_state(state)
    if install_year is None:
        install_year = datetime.now(tz=UTC).year
        assumptions.append(f"install_year not provided; defaulted to {install_year}")

    federal = federal_incentives(install_year)
    programs = state_programs(store, state)
    vintage = snapshot_vintage(store)

    warnings: list[str] = []
    if vintage is None:
        warnings.append(
            "DSIRE snapshot not synced — state/local programs unavailable; "
            "federal incentives only. " + DSIRE_DOWNLOAD_HELP
        )
    else:
        assumptions.append(
            f"state/local programs from DSIRE snapshot vintage {vintage.vintage} "
            f"(loaded {vintage.loaded_at})"
        )

    return ToolResult(
        data={
            "state": state,
            "federal": [item.model_dump() for item in federal],
            "state_local": [item.model_dump() for item in programs],
            "snapshot_vintage": vintage.vintage if vintage else None,
        },
        units=_INCENTIVE_UNITS,
        source=SourceRef(
            name="Federal ITC table + DSIRE snapshot",
            url="https://programs.dsireusa.org",
            retrieved_at=vintage.loaded_at if vintage else utc_now_iso(),
            license=DSIRE.license_note,
        ),
        assumptions=assumptions,
        warnings=warnings,
    )


async def sync_incentives(
    store: BulkStore, *, source: str, vintage: str | None = None
) -> ToolResult:
    """Load a DSIRE program export (local path or https URL) into the bulk store."""
    vintage, assumptions = default_vintage(vintage)

    if "://" in source:
        csv_path = await fetch_to_tempfile(source, config=DSIRE)
        cleanup = csv_path
    else:
        csv_path = resolve_local_data_file(source)
        cleanup = None
    try:
        async with store.write_lock:
            count = await asyncio.to_thread(sync_snapshot, store, csv_path, vintage)
    except ValueError as exc:
        raise BadInput(field="source", value=source, allowed=str(exc)) from exc
    finally:
        if cleanup is not None:
            cleanup.unlink(missing_ok=True)

    return sync_result(
        dataset=DSIRE_DATASET,
        rows_loaded=count,
        vintage=vintage,
        source_name="DSIRE program snapshot",
        source_url=source,
        license_note=DSIRE.license_note,
        assumptions=assumptions,
    )
