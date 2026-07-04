from pathlib import Path

from solar_mcp_core.cache import HttpCache, canonicalize


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_cache(tmp_path: Path, clock: FakeClock) -> HttpCache:
    return HttpCache(path=tmp_path / "http.db", clock=clock)


class TestCanonicalize:
    def test_params_sorted(self) -> None:
        a = canonicalize("https://x.gov", "/api", {"lat": 40, "lon": -105})
        b = canonicalize("https://x.gov", "/api", {"lon": -105, "lat": 40})
        assert a == b

    def test_api_key_excluded(self) -> None:
        with_key = canonicalize("https://x.gov", "/api", {"lat": 40, "api_key": "SECRET"})
        without = canonicalize("https://x.gov", "/api", {"lat": 40})
        assert with_key == without
        assert "SECRET" not in with_key

    def test_whole_floats_normalized_to_ints(self) -> None:
        as_float = canonicalize("https://x.gov", "/api", {"tilt": 20.0})
        as_int = canonicalize("https://x.gov", "/api", {"tilt": 20})
        assert as_float == as_int

    def test_fractional_floats_distinct(self) -> None:
        a = canonicalize("https://x.gov", "/api", {"tilt": 20.5})
        b = canonicalize("https://x.gov", "/api", {"tilt": 20.6})
        assert a != b

    def test_slash_handling(self) -> None:
        a = canonicalize("https://x.gov/", "/api/v1", {})
        b = canonicalize("https://x.gov", "api/v1", {})
        assert a == b


class TestHttpCache:
    def test_miss_returns_none(self, tmp_path: Path) -> None:
        cache = make_cache(tmp_path, FakeClock())
        assert cache.get("nope") is None

    def test_fresh_hit(self, tmp_path: Path) -> None:
        clock = FakeClock()
        cache = make_cache(tmp_path, clock)
        cache.put("k", "nrel", 200, '{"a": 1}', ttl_seconds=100)
        entry = cache.get("k")
        assert entry is not None
        assert entry.body == '{"a": 1}'
        assert entry.status == 200

    def test_expired_entry_not_served(self, tmp_path: Path) -> None:
        clock = FakeClock()
        cache = make_cache(tmp_path, clock)
        cache.put("k", "nrel", 200, "{}", ttl_seconds=100)
        clock.advance(101)
        assert cache.get("k") is None

    def test_expired_entry_served_when_stale_allowed(self, tmp_path: Path) -> None:
        clock = FakeClock()
        cache = make_cache(tmp_path, clock)
        cache.put("k", "nrel", 200, "{}", ttl_seconds=100)
        clock.advance(101)
        entry = cache.get("k", allow_stale=True)
        assert entry is not None
        assert not entry.is_fresh(clock())

    def test_put_replaces_existing(self, tmp_path: Path) -> None:
        clock = FakeClock()
        cache = make_cache(tmp_path, clock)
        cache.put("k", "nrel", 200, "old", ttl_seconds=100)
        cache.put("k", "nrel", 200, "new", ttl_seconds=100)
        entry = cache.get("k")
        assert entry is not None
        assert entry.body == "new"

    def test_persists_across_instances(self, tmp_path: Path) -> None:
        clock = FakeClock()
        first = make_cache(tmp_path, clock)
        first.put("k", "nrel", 200, "{}", ttl_seconds=100)
        first.close()
        second = make_cache(tmp_path, clock)
        assert second.get("k") is not None
