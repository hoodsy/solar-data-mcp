"""Bulk dataset loaders: Tracking the Sun and SolarTRACE into the DuckDB store.

Both accept a local file path or an https URL and stream the file (never held
in memory). Loads are stage-validate-swap: the file lands in a scratch table,
is validated and transformed there, and only a fully successful load replaces
the live table and records the new vintage — a bad file can never corrupt a
previous good snapshot or its provenance. The blocking DuckDB work runs in a
thread so multi-GB syncs don't stall the MCP event loop.
"""

import asyncio
from pathlib import Path

from solar_mcp_core.bulk import (
    SOLARTRACE_DATASET,
    SOLARTRACE_TABLE,
    TTS_DATASET,
    TTS_TABLE,
    BulkStore,
    fetch_to_tempfile,
)
from solar_mcp_core.config import SOLARTRACE, TRACKING_THE_SUN
from solar_mcp_core.errors import BadInput

# Canonical columns, or LBNL's raw names which we derive them from.
TTS_CANONICAL = ("state", "year", "price_per_watt", "size_kw")
TTS_LBNL = ("state", "installed_price", "system_size_DC")

SOLARTRACE_REQUIRED = (
    "state",
    "jurisdiction",
    "median_permit_days",
    "median_inspection_days",
    "median_pto_days",
)

_STAGING = "sync_staging"


def _columns(store: BulkStore, table: str) -> set[str]:
    return {str(row[0]) for row in store.query(f'DESCRIBE "{table}"')}


async def _to_local_file(source: str, source_name: str) -> tuple[Path, bool]:
    """(path, is_temporary). URLs stream to a temp file the caller deletes."""
    if source.startswith(("http://", "https://")):
        return await fetch_to_tempfile(source, source=source_name), True
    path = Path(source)
    if not path.is_file():
        raise BadInput(field="source", value=source, allowed="existing file path or https URL")
    return path, False


def _stage(store: BulkStore, source: str, path: Path) -> set[str]:
    try:
        store.stage_csv(_STAGING, path)
    except Exception as exc:
        store.execute(f'DROP TABLE IF EXISTS "{_STAGING}"')
        raise BadInput(
            field="source",
            value=source,
            allowed=f"a readable CSV file ({type(exc).__name__}: {exc})",
        ) from exc
    return _columns(store, _STAGING)


def _load_tts_sync(
    store: BulkStore, source: str, path: Path, vintage: str, state: str | None
) -> int:
    columns = _stage(store, source, path)
    try:
        if all(c in columns for c in TTS_CANONICAL):
            price, size, year = "price_per_watt", "size_kw", "year"
            sane = "price_per_watt > 0"  # guards zero/sentinel rows in curated exports
        elif all(c in columns for c in TTS_LBNL):
            price = "installed_price / (system_size_DC * 1000.0)"
            size = "system_size_DC"
            year = "year" if "year" in columns else "NULL"
            # LBNL encodes missing values as -9999 sentinels; without this
            # filter they poison every median downstream.
            sane = "installed_price > 0 AND system_size_DC > 0"
        else:
            raise BadInput(
                field="source",
                value=source,
                allowed=(
                    f"a Tracking the Sun export with columns {TTS_CANONICAL} "
                    f"or LBNL raw columns {TTS_LBNL}; got {sorted(columns)}"
                ),
            )

        module = next(
            (c for c in ("module_manufacturer_1", "module_manufacturer") if c in columns), "NULL"
        )
        inverter = next(
            (c for c in ("inverter_manufacturer_1", "inverter_manufacturer") if c in columns),
            "NULL",
        )
        where = f"WHERE {sane}" + (" AND upper(state) = ?" if state else "")
        params = [state] if state else []
        try:
            store.execute(
                f"CREATE OR REPLACE TABLE {TTS_TABLE} AS "
                f"SELECT upper(state) AS state, {year} AS year, "
                f"{price} AS price_per_watt, {size} AS size_kw, "
                f"{module} AS module_manufacturer, {inverter} AS inverter_manufacturer "
                f'FROM "{_STAGING}" {where}',
                params,
            )
        except Exception as exc:  # e.g. non-numeric price/size columns
            raise BadInput(
                field="source",
                value=source,
                allowed=f"numeric price/size columns (transform failed: {exc})",
            ) from exc
        store.set_vintage(TTS_DATASET, vintage)
        row = store.query(f"SELECT count(*) FROM {TTS_TABLE}")
        return int(row[0][0])
    finally:
        store.execute(f'DROP TABLE IF EXISTS "{_STAGING}"')


async def load_tracking_the_sun(
    store: BulkStore, *, source: str, vintage: str, state: str | None = None
) -> int:
    """Load a Tracking the Sun release; returns rows loaded.

    Accepts either canonical columns (state, year, price_per_watt, size_kw,
    optional module/inverter manufacturer) or LBNL's raw names
    (installed_price, system_size_DC) from which $/W is derived. Optional
    state filter keeps the local store small.
    """
    path, is_temp = await _to_local_file(source, TRACKING_THE_SUN.name)
    try:
        return await asyncio.to_thread(_load_tts_sync, store, source, path, vintage, state)
    finally:
        if is_temp:
            path.unlink(missing_ok=True)


def _load_solartrace_sync(store: BulkStore, source: str, path: Path, vintage: str) -> int:
    columns = _stage(store, source, path)
    try:
        missing = [c for c in SOLARTRACE_REQUIRED if c not in columns]
        if missing:
            raise BadInput(
                field="source",
                value=source,
                allowed=f"a SolarTRACE export with columns {SOLARTRACE_REQUIRED} "
                f"(missing {missing})",
            )
        store.execute(f'CREATE OR REPLACE TABLE {SOLARTRACE_TABLE} AS SELECT * FROM "{_STAGING}"')
        store.set_vintage(SOLARTRACE_DATASET, vintage)
        row = store.query(f"SELECT count(*) FROM {SOLARTRACE_TABLE}")
        return int(row[0][0])
    finally:
        store.execute(f'DROP TABLE IF EXISTS "{_STAGING}"')


async def load_solartrace(store: BulkStore, *, source: str, vintage: str) -> int:
    path, is_temp = await _to_local_file(source, SOLARTRACE.name)
    try:
        return await asyncio.to_thread(_load_solartrace_sync, store, source, path, vintage)
    finally:
        if is_temp:
            path.unlink(missing_ok=True)
