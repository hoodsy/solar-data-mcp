"""The result envelope every solar-data-mcp tool returns.

One contract across all servers: data + units + source + assumptions + warnings.
Agents learn it once and can always tell what a number means, where it came from,
and which defaults were injected on their behalf.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

REPO_URL = "https://github.com/loganbernard/solar-data-mcp"


class SourceRef(BaseModel):
    """Provenance for a tool result."""

    name: str
    url: str
    retrieved_at: str  # ISO 8601, UTC
    license: str


class ToolResult(BaseModel):
    """Envelope returned by every tool.

    Design rule: never silently default. Every parameter the tool filled in for
    the caller must appear as a line in ``assumptions``.
    """

    data: dict[str, Any]
    units: dict[str, str] = Field(default_factory=dict)
    source: SourceRef
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def composite_source_ref() -> SourceRef:
    """SourceRef for composite tools whose real provenance is the audit trail."""
    return SourceRef(
        name="solar-data-mcp composite (see audit_trail)",
        url=REPO_URL,
        retrieved_at=utc_now_iso(),
        license="components individually licensed; see audit_trail",
    )


def audit_entry(component: str, source: SourceRef) -> dict[str, str]:
    """One audit-trail row: which component a composite got from which source."""
    return {
        "component": component,
        "source": source.name,
        "url": source.url,
        "retrieved_at": source.retrieved_at,
    }


def user_audit_entry(component: str) -> dict[str, str]:
    return {"component": component, "source": "user-provided", "url": "", "retrieved_at": "n/a"}
