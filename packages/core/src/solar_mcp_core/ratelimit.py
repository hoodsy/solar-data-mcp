"""Async token-bucket rate limiter with injectable clock and sleep (for tests)."""

import asyncio
import time
from collections.abc import Awaitable, Callable


class TokenBucket:
    def __init__(
        self,
        capacity: float,
        refill_per_second: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if capacity < 1:
            raise ValueError(
                "capacity must be >= 1 — a bucket that can never hold a "
                "full token would block acquire() forever"
            )
        if refill_per_second <= 0:
            raise ValueError("refill_per_second must be positive")
        self._capacity = capacity
        self._refill_per_second = refill_per_second
        self._clock = clock
        self._sleep = sleep
        self._tokens = capacity
        self._last_refill = clock()
        self._lock = asyncio.Lock()

    @classmethod
    def per_hour(
        cls,
        requests_per_hour: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> "TokenBucket":
        return cls(
            capacity=float(requests_per_hour),
            refill_per_second=requests_per_hour / 3600.0,
            clock=clock,
            sleep=sleep,
        )

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._last_refill
        self._last_refill = now
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_second)

    async def acquire(self) -> None:
        """Take one token, sleeping until one is available."""
        async with self._lock:
            self._refill()
            while self._tokens < 1:
                deficit = 1 - self._tokens
                await self._sleep(deficit / self._refill_per_second)
                self._refill()
            self._tokens -= 1

    @property
    def available(self) -> float:
        self._refill()
        return self._tokens
