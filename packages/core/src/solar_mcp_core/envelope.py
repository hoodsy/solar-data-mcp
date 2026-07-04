"""The result envelope every solar-data-mcp tool returns.

One contract across all servers: data + units + source + assumptions + warnings.
Agents learn it once and can always tell what a number means, where it came from,
and which defaults were injected on their behalf.
"""

from typing import Any

from pydantic import BaseModel, Field


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
