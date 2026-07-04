import pytest
from solar_mcp_core.ratelimit import TokenBucket


class FakeTime:
    """Clock + sleep pair: sleeping advances the clock, no real waiting."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.mark.anyio
async def test_acquire_within_capacity_never_sleeps() -> None:
    fake = FakeTime()
    bucket = TokenBucket(capacity=3, refill_per_second=1, clock=fake.clock, sleep=fake.sleep)
    for _ in range(3):
        await bucket.acquire()
    assert fake.slept == []


@pytest.mark.anyio
async def test_acquire_sleeps_when_depleted() -> None:
    fake = FakeTime()
    bucket = TokenBucket(capacity=1, refill_per_second=0.5, clock=fake.clock, sleep=fake.sleep)
    await bucket.acquire()
    await bucket.acquire()  # must wait ~2s for one token at 0.5/s
    assert len(fake.slept) == 1
    assert fake.slept[0] == pytest.approx(2.0)


@pytest.mark.anyio
async def test_refill_caps_at_capacity() -> None:
    fake = FakeTime()
    bucket = TokenBucket(capacity=2, refill_per_second=1, clock=fake.clock, sleep=fake.sleep)
    fake.now += 100  # long idle must not accumulate beyond capacity
    assert bucket.available == pytest.approx(2)


@pytest.mark.anyio
async def test_per_hour_constructor() -> None:
    fake = FakeTime()
    bucket = TokenBucket.per_hour(1000, clock=fake.clock, sleep=fake.sleep)
    assert bucket.available == pytest.approx(1000)
    await bucket.acquire()
    assert bucket.available == pytest.approx(999)


def test_invalid_construction_rejected() -> None:
    with pytest.raises(ValueError):
        TokenBucket(capacity=0, refill_per_second=1)
    with pytest.raises(ValueError):
        TokenBucket(capacity=1, refill_per_second=0)
