"""Shared test doubles for core tests."""

import httpx


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


class ScriptedTransport(httpx.AsyncBaseTransport):
    """Returns queued responses in order; records every request it saw."""

    def __init__(self, responses: list[httpx.Response | Exception]) -> None:
        self.queue = list(responses)
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
