"""DuckDB-backed bulk store: the second cache tier, for datasets too large
for the HTTP cache (DSIRE snapshots, Tracking the Sun, SolarTRACE).

Populated only by explicit `sync_*` tools — never implicitly — and every
dataset records its vintage so query results can cite how fresh the data is.
The `duckdb` dependency is declared by the packages that use this module
(solar-data-mcp-economics, solar-data-mcp-market), keeping solar-data-mcp-core
lightweight.
"""

import asyncio
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from solar_mcp_core import units
from solar_mcp_core.config import (
    SourceConfig,
    cache_dir,
    ensure_private_dir,
    harden_file_perms,
)
from solar_mcp_core.envelope import SourceRef, ToolResult, utc_now_iso
from solar_mcp_core.errors import BadInput, SourceUnavailable
from solar_mcp_core.net import assert_allowed_download_url

_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS _meta (
    dataset TEXT PRIMARY KEY,
    vintage TEXT NOT NULL,
    loaded_at TEXT NOT NULL,
    schema_version INTEGER NOT NULL
)
"""

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Shared-dataset contract: these names are used across packages (economics
# reads the Tracking the Sun table that market syncs), so they live here.
TTS_DATASET = "tts"
TTS_TABLE = "tts_systems"
SOLARTRACE_DATASET = "solartrace"
SOLARTRACE_TABLE = "solartrace"
DSIRE_DATASET = "dsire_programs"
DSIRE_TABLE = "dsire_programs"


@dataclass
class DatasetVintage:
    dataset: str
    vintage: str
    loaded_at: str  # ISO 8601 UTC
    schema_version: int


class BulkStore:
    def __init__(self, path: Path | str | None = None) -> None:
        """Open (or create) the bulk store. Pass ":memory:" for tests."""
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover — dev/CI envs always have it
            raise RuntimeError(
                "BulkStore needs the 'duckdb' package. It is installed automatically "
                "with solar-data-mcp-economics and solar-data-mcp-market; for "
                "standalone use: pip install duckdb"
            ) from exc
        db = path if path is not None else cache_dir() / "bulk.duckdb"
        if isinstance(db, Path):
            ensure_private_dir(db.parent)  # bulk store holds locally synced data
        self._conn = duckdb.connect(str(db))
        if isinstance(db, Path):
            harden_file_perms(db)
        self._conn.execute(_META_SCHEMA)
        # Serializes sync_* stage-validate-swap sections. The umbrella shares one
        # store across all tool families, and every sync uses the same staging
        # table on a single (non-thread-safe) DuckDB connection, so concurrent
        # syncs must not overlap.
        self.write_lock = asyncio.Lock()

    def stage_csv(self, table: str, csv_path: Path) -> int:
        """Load a CSV into `table` WITHOUT touching any vintage; return row count.

        DuckDB streams the file — it is never held in memory, which is what
        makes multi-GB sources like Tracking the Sun tractable. Sync loaders
        stage into a scratch table, validate, swap, and only then record the
        vintage — so a bad file can never corrupt a good snapshot or its
        provenance.
        """
        _check_identifier(table)
        self._conn.execute(
            f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM read_csv_auto(?)',
            [str(csv_path)],
        )
        row = self._conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()
        return int(row[0]) if row else 0

    def set_vintage(self, dataset: str, vintage: str, schema_version: int = 1) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO _meta VALUES (?, ?, ?, ?)",
            [dataset, vintage, utc_now_iso(), schema_version],
        )

    def load_csv(
        self,
        dataset: str,
        table: str,
        csv_path: Path,
        vintage: str,
        schema_version: int = 1,
    ) -> int:
        """stage_csv + set_vintage in one step, for loads needing no validation
        or transform between the two."""
        count = self.stage_csv(table, csv_path)
        self.set_vintage(dataset, vintage, schema_version)
        return count

    def vintage(self, dataset: str) -> DatasetVintage | None:
        row = self._conn.execute(
            "SELECT dataset, vintage, loaded_at, schema_version FROM _meta WHERE dataset = ?",
            [dataset],
        ).fetchone()
        if row is None:
            return None
        return DatasetVintage(*row)

    def has_table(self, table: str) -> bool:
        _check_identifier(table)
        row = self._conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
        ).fetchone()
        return bool(row and row[0])

    def query(self, sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
        """Run a read query. Callers own the SQL; parameters are always bound."""
        result = self._conn.execute(sql, params or [])
        return [tuple(row) for row in result.fetchall()]

    def execute(self, sql: str, params: list[Any] | None = None) -> None:
        """Run DDL/DML (CREATE TABLE AS, DROP) — for sync loaders' transforms."""
        self._conn.execute(sql, params or [])

    def close(self) -> None:
        self._conn.close()


def _check_identifier(name: str) -> None:
    if not _IDENTIFIER.match(name):
        raise ValueError(f"invalid table name: {name!r}")


# Ceiling above the largest real dataset (Tracking the Sun is ~1-2 GB); bounds
# disk use from a hostile or misconfigured endpoint without blocking real files.
MAX_DOWNLOAD_BYTES = 4 * 1024**3
_STREAM_TIMEOUT = 60.0  # per-connect/read; a stall aborts the socket
_TOTAL_TIMEOUT = 3600.0  # wall-clock ceiling; defeats a slow-drip that resets read timeouts


async def fetch_to_tempfile(url: str, *, config: SourceConfig, suffix: str = ".csv") -> Path:
    """Stream a dataset's bulk file to a temp path (sync_* tools); caller deletes it.

    Restricted to the dataset's official https host (see net.assert_allowed_download_url):
    the agent-supplied `source` is untrusted, so this must not become an SSRF or
    internal-fetch primitive. Redirects are refused, and the transfer is bounded
    in both size and wall-clock time. Plain httpx rather than SolarHttpClient —
    bulk files are not JSON and must never enter the HTTP cache tier.
    """
    assert_allowed_download_url(url, config)
    descriptor, name = tempfile.mkstemp(suffix=suffix)
    os.close(descriptor)
    path = Path(name)
    try:
        await asyncio.wait_for(_stream_to_file(url, config.name, path), _TOTAL_TIMEOUT)
    except TimeoutError as exc:
        path.unlink(missing_ok=True)
        raise SourceUnavailable(config.name, f"download exceeded {_TOTAL_TIMEOUT:.0f}s") from exc
    except httpx.TransportError as exc:
        path.unlink(missing_ok=True)
        raise SourceUnavailable(config.name, f"download failed: {type(exc).__name__}") from exc
    except BaseException:
        # BadInput, HTTP-status/size failures, cancellation — never leak the temp file.
        path.unlink(missing_ok=True)
        raise
    return path


async def _stream_to_file(url: str, source: str, path: Path) -> None:
    async with (
        httpx.AsyncClient(follow_redirects=False, timeout=_STREAM_TIMEOUT) as client,
        client.stream("GET", url) as response,
    ):
        if response.is_redirect:
            raise BadInput(
                field="source",
                value=url,
                allowed=(
                    "a direct download URL (redirects are refused; "
                    "pass the final URL or a local file)"
                ),
            )
        if response.status_code != 200:
            raise SourceUnavailable(source, f"download failed: HTTP {response.status_code}")
        declared = response.headers.get("Content-Length")
        if declared is not None and declared.isdigit() and int(declared) > MAX_DOWNLOAD_BYTES:
            raise SourceUnavailable(
                source, f"file too large ({declared} bytes; cap {MAX_DOWNLOAD_BYTES})"
            )
        written = 0
        with path.open("wb") as out:
            async for chunk in response.aiter_bytes():
                written += len(chunk)
                if written > MAX_DOWNLOAD_BYTES:
                    raise SourceUnavailable(
                        source, f"download exceeded size cap of {MAX_DOWNLOAD_BYTES} bytes"
                    )
                out.write(chunk)


def default_vintage(vintage: str | None) -> tuple[str, list[str]]:
    """Today's date when the caller gave no vintage, with the assumption line."""
    if vintage is not None:
        return vintage, []
    today = utc_now_iso()[:10]
    return today, [f"vintage not provided; defaulted to today ({today})"]


def sync_result(
    *,
    dataset: str,
    rows_loaded: int,
    vintage: str,
    source_name: str,
    source_url: str,
    license_note: str,
    assumptions: list[str],
    extra_data: dict[str, Any] | None = None,
) -> ToolResult:
    """The one envelope shape every sync_* tool returns."""
    data: dict[str, Any] = {"dataset": dataset, "rows_loaded": rows_loaded, "vintage": vintage}
    units_map = {"dataset": units.LABEL, "rows_loaded": units.COUNT, "vintage": units.LABEL}
    for key in extra_data or {}:
        units_map[key] = units.LABEL
    data.update(extra_data or {})
    return ToolResult(
        data=data,
        units=units_map,
        source=SourceRef(
            name=source_name, url=source_url, retrieved_at=utc_now_iso(), license=license_note
        ),
        assumptions=assumptions,
        warnings=[],
    )
