"""get_incentives and sync_incentives: federal ITC table + DSIRE snapshots."""

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
from solar_mcp_core import units
from solar_mcp_core.bulk import BulkStore
from solar_mcp_core.config import DSIRE
from solar_mcp_core.envelope import SourceRef, ToolResult
from solar_mcp_core.errors import BadInput, SourceUnavailable

from solar_mcp_economics.economics import ITC_CITATION
from solar_mcp_economics.incentives import (
    DSIRE_DOWNLOAD_HELP,
    federal_incentives,
    snapshot_vintage,
    state_programs,
    sync_snapshot,
)
from solar_mcp_economics.models import validate_state

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
        assumptions.append(f"install_year not provided; assumed {install_year}")

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
            retrieved_at=vintage.loaded_at if vintage else _now_iso(),
            license=DSIRE.license_note,
        ),
        assumptions=assumptions,
        warnings=warnings,
    )


async def sync_incentives(
    store: BulkStore, *, source: str, vintage: str | None = None
) -> ToolResult:
    """Load a DSIRE program export (local path or https URL) into the bulk store."""
    assumptions: list[str] = []
    if vintage is None:
        vintage = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        assumptions.append(f"vintage not provided; recorded as today ({vintage})")

    if source.startswith(("http://", "https://")):
        csv_path = await _download(source)
        cleanup = csv_path
    else:
        csv_path = Path(source)
        cleanup = None
        if not csv_path.is_file():
            raise BadInput(
                field="source",
                value=source,
                allowed=f"existing CSV path or https URL. {DSIRE_DOWNLOAD_HELP}",
            )
    try:
        count = sync_snapshot(store, csv_path, vintage=vintage)
    except ValueError as exc:
        raise BadInput(field="source", value=source, allowed=str(exc)) from exc
    finally:
        if cleanup is not None:
            cleanup.unlink(missing_ok=True)

    return ToolResult(
        data={"dataset": "dsire_programs", "rows_loaded": count, "vintage": vintage},
        units={
            "dataset": units.LABEL,
            "rows_loaded": units.COUNT,
            "vintage": units.ISO_DATE,
        },
        source=SourceRef(
            name="DSIRE program snapshot",
            url=source,
            retrieved_at=_now_iso(),
            license=DSIRE.license_note,
        ),
        assumptions=assumptions,
        warnings=[],
    )


async def _download(url: str) -> Path:
    descriptor, name = tempfile.mkstemp(suffix=".csv")
    os.close(descriptor)
    path = Path(name)
    try:
        async with (
            httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client,
            client.stream("GET", url) as response,
        ):
            if response.status_code != 200:
                raise SourceUnavailable(
                    DSIRE.name, f"snapshot download failed: HTTP {response.status_code}"
                )
            with path.open("wb") as out:
                async for chunk in response.aiter_bytes():
                    out.write(chunk)
    except httpx.TransportError as exc:
        path.unlink(missing_ok=True)
        raise SourceUnavailable(DSIRE.name, f"snapshot download failed: {exc}") from exc
    return path


def _now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
