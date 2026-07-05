"""Bulk dataset loaders: Tracking the Sun and SolarTRACE into the DuckDB store.

Both accept a local file path or an https URL, stream the file (never held in
memory), normalize into a stable schema, and record the dataset vintage that
every query result cites. Column mapping is explicit and validated — a wrong
export fails loudly with the list of expected columns.
"""

from pathlib import Path

from solar_mcp_core.bulk import BulkStore, fetch_to_tempfile
from solar_mcp_core.config import SOLARTRACE, TRACKING_THE_SUN
from solar_mcp_core.errors import BadInput

TTS_DATASET = "tts"
TTS_TABLE = "tts_systems"
# Canonical columns, or LBNL's raw names which we derive them from.
TTS_CANONICAL = ("state", "year", "price_per_watt", "size_kw")
TTS_LBNL = ("state", "installed_price", "system_size_DC")

SOLARTRACE_DATASET = "solartrace"
SOLARTRACE_TABLE = "solartrace"
SOLARTRACE_REQUIRED = (
    "state",
    "jurisdiction",
    "median_permit_days",
    "median_inspection_days",
    "median_pto_days",
)


def _columns(store: BulkStore, table: str) -> set[str]:
    return {str(row[0]) for row in store.query(f"DESCRIBE {table}")}


async def _to_local_file(source: str, source_name: str) -> tuple[Path, bool]:
    """(path, is_temporary). URLs stream to a temp file the caller deletes."""
    if source.startswith(("http://", "https://")):
        return await fetch_to_tempfile(source, source=source_name), True
    path = Path(source)
    if not path.is_file():
        raise BadInput(field="source", value=source, allowed="existing file path or https URL")
    return path, False


async def load_tracking_the_sun(
    store: BulkStore, *, source: str, vintage: str, state: str | None = None
) -> int:
    """Load a Tracking the Sun release; returns rows loaded.

    Accepts either canonical columns (state, year, price_per_watt, size_kw,
    optional module_manufacturer/inverter_manufacturer) or LBNL's raw names
    (installed_price, system_size_DC) from which $/W is derived. Optional
    state filter keeps the local store small.
    """
    path, is_temp = await _to_local_file(source, TRACKING_THE_SUN.name)
    try:
        store.load_csv(TTS_DATASET, "tts_raw", path, vintage=vintage)
        columns = _columns(store, "tts_raw")

        if all(c in columns for c in TTS_CANONICAL):
            price = "price_per_watt"
            size = "size_kw"
            year = "year"
        elif all(c in columns for c in TTS_LBNL):
            price = "installed_price / (system_size_DC * 1000.0)"
            size = "system_size_DC"
            year = "year" if "year" in columns else "NULL"
        else:
            raise BadInput(
                field="source",
                value=source,
                allowed=(
                    f"a Tracking the Sun export with columns {TTS_CANONICAL} "
                    f"or LBNL raw columns {TTS_LBNL}; got {sorted(columns)}"
                ),
            )

        module = (
            "module_manufacturer_1"
            if "module_manufacturer_1" in columns
            else ("module_manufacturer" if "module_manufacturer" in columns else "NULL")
        )
        inverter = (
            "inverter_manufacturer_1"
            if "inverter_manufacturer_1" in columns
            else ("inverter_manufacturer" if "inverter_manufacturer" in columns else "NULL")
        )
        where = "WHERE upper(state) = ?" if state else ""
        params = [state] if state else []
        store.execute(
            f"CREATE OR REPLACE TABLE {TTS_TABLE} AS "
            f"SELECT upper(state) AS state, {year} AS year, "
            f"{price} AS price_per_watt, {size} AS size_kw, "
            f"{module} AS module_manufacturer, {inverter} AS inverter_manufacturer "
            f"FROM tts_raw {where}",
            params,
        )
        store.execute("DROP TABLE tts_raw")
        row = store.query(f"SELECT count(*) FROM {TTS_TABLE}")
        return int(row[0][0])
    finally:
        if is_temp:
            path.unlink(missing_ok=True)


async def load_solartrace(store: BulkStore, *, source: str, vintage: str) -> int:
    path, is_temp = await _to_local_file(source, SOLARTRACE.name)
    try:
        count = store.load_csv(SOLARTRACE_DATASET, SOLARTRACE_TABLE, path, vintage=vintage)
        columns = _columns(store, SOLARTRACE_TABLE)
        missing = [c for c in SOLARTRACE_REQUIRED if c not in columns]
        if missing:
            raise BadInput(
                field="source",
                value=source,
                allowed=f"a SolarTRACE export with columns {SOLARTRACE_REQUIRED} "
                f"(missing {missing})",
            )
        return count
    finally:
        if is_temp:
            path.unlink(missing_ok=True)
