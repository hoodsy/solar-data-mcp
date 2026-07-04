"""Error taxonomy shared by all solar-data-mcp servers.

Agents self-correct well when errors are specific: BadInput always names the
offending field and its allowed range; QuotaExceeded says when capacity returns.
"""


class SolarMCPError(Exception):
    """Base class for all solar-data-mcp errors."""


class BadInput(SolarMCPError):
    """Input rejected before any HTTP call was made."""

    def __init__(self, field: str, value: object, allowed: str) -> None:
        self.field = field
        self.value = value
        self.allowed = allowed
        super().__init__(f"{field}={value!r} invalid: allowed {allowed}")


class QuotaExceeded(SolarMCPError):
    """The source's rate limit was hit (HTTP 429)."""

    def __init__(self, source: str, remaining: int | None = None) -> None:
        self.source = source
        self.remaining = remaining
        detail = f"X-RateLimit-Remaining={remaining}" if remaining is not None else "limit reached"
        super().__init__(
            f"{source} rate limit exceeded ({detail}). The limit is a rolling "
            "hourly window; capacity returns within 60 minutes of earlier requests. "
            "Cached results are served where available."
        )


class SourceUnavailable(SolarMCPError):
    """The upstream source failed (5xx, timeout, or an error in its response body)."""

    def __init__(self, source: str, detail: str) -> None:
        self.source = source
        self.detail = detail
        super().__init__(f"{source} unavailable: {detail}")
