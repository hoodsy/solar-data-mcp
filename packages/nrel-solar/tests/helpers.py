"""Shared assertions for nrel-solar tool tests."""

from solar_mcp_core.envelope import ToolResult


def assert_envelope(result: ToolResult, *, expect_assumptions: bool = True) -> None:
    """Assert the envelope contract every tool must honor.

    - data is non-empty
    - every data field has a units entry (containers included — one unit per key)
    - source is fully populated
    - assumptions are present whenever defaults were injected
    """
    assert result.data, "data must be non-empty"
    for field in result.data:
        assert field in result.units, f"data field {field!r} has no units entry"
    assert result.source.name
    assert result.source.url
    assert result.source.retrieved_at
    assert result.source.license
    if expect_assumptions:
        assert result.assumptions, "defaults were injected but assumptions is empty"
