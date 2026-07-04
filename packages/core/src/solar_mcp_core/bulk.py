"""DuckDB-backed bulk store: the second cache tier, for datasets too large
for the HTTP cache (DSIRE snapshots, Tracking the Sun, SolarTRACE).

Populated only by explicit `sync_*` tools — never implicitly — and every
dataset records its vintage so query results can cite how fresh the data is.
The `duckdb` dependency is declared by the packages that use this module
(solar-mcp-economics, solar-mcp-market), keeping solar-mcp-core lightweight.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from solar_mcp_core.config import cache_dir

_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS _meta (
    dataset TEXT PRIMARY KEY,
    vintage TEXT NOT NULL,
    loaded_at TEXT NOT NULL,
    schema_version INTEGER NOT NULL
)
"""

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
                "with solar-mcp-economics and solar-mcp-market; for standalone use: "
                "pip install duckdb"
            ) from exc
        db = path if path is not None else cache_dir() / "bulk.duckdb"
        if isinstance(db, Path):
            db.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(db))
        self._conn.execute(_META_SCHEMA)

    def load_csv(
        self,
        dataset: str,
        table: str,
        csv_path: Path,
        vintage: str,
        schema_version: int = 1,
    ) -> int:
        """(Re)load a CSV into `table`, record the dataset vintage, return row count.

        DuckDB streams the file — it is never held in memory, which is what
        makes multi-GB sources like Tracking the Sun tractable.
        """
        _check_identifier(table)
        self._conn.execute(
            f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM read_csv_auto(?)',
            [str(csv_path)],
        )
        row = self._conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()
        count = int(row[0]) if row else 0
        self._conn.execute(
            "INSERT OR REPLACE INTO _meta VALUES (?, ?, ?, ?)",
            [dataset, vintage, _now_iso(), schema_version],
        )
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

    def close(self) -> None:
        self._conn.close()


def _check_identifier(name: str) -> None:
    if not _IDENTIFIER.match(name):
        raise ValueError(f"invalid table name: {name!r}")


def _now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
