"""SQLite HTTP cache keyed on canonicalized URL+params.

Caching is a correctness feature here, not just a UX one: NREL's rate limit is
1,000 req/hr shared across all its APIs, and TMY-based results are deterministic
per location+params, so a 30-day TTL eliminates most repeat traffic. Stale
entries are kept and can be served explicitly when the quota is exhausted.
"""

import sqlite3
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

from solar_mcp_core.config import cache_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS http_cache (
    key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    status INTEGER NOT NULL,
    body TEXT NOT NULL,
    retrieved_at REAL NOT NULL,
    expires_at REAL NOT NULL
)
"""


def canonicalize(base_url: str, path: str, params: Mapping[str, object]) -> str:
    """Stable cache/fixture key for a request: sorted params, api_key excluded.

    The api_key is excluded so cache entries survive key rotation and recorded
    fixtures never embed a secret in their key.
    """
    filtered = {k: _normalize(v) for k, v in sorted(params.items()) if k != "api_key"}
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}?{urlencode(filtered)}"


def _normalize(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


@dataclass
class CacheEntry:
    key: str
    source: str
    status: int
    body: str
    retrieved_at: float
    expires_at: float

    def is_fresh(self, now: float) -> bool:
        return now < self.expires_at


class HttpCache:
    def __init__(
        self,
        path: Path | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._clock = clock
        db_path = path if path is not None else cache_dir() / "http.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def get(self, key: str, *, allow_stale: bool = False) -> CacheEntry | None:
        row = self._conn.execute(
            "SELECT key, source, status, body, retrieved_at, expires_at"
            " FROM http_cache WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        entry = CacheEntry(*row)
        if entry.is_fresh(self._clock()) or allow_stale:
            return entry
        return None

    def put(self, key: str, source: str, status: int, body: str, ttl_seconds: int) -> CacheEntry:
        now = self._clock()
        entry = CacheEntry(
            key=key,
            source=source,
            status=status,
            body=body,
            retrieved_at=now,
            expires_at=now + ttl_seconds,
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO http_cache VALUES (?, ?, ?, ?, ?, ?)",
            (key, source, status, body, entry.retrieved_at, entry.expires_at),
        )
        self._conn.commit()
        return entry

    def close(self) -> None:
        self._conn.close()
