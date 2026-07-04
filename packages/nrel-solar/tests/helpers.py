"""Shared assertions for nrel-solar tool tests."""

from solar_mcp_core.envelope import ToolResult


def assert_envelope(result: ToolResult) -> None:
    """Assert the envelope contract every tool must honor.

    - data is non-empty
    - every data field is covered by units: either an exact entry, or
      dotted/list-item entries for nested payloads ("best.tilt_deg",
      "ranked[].ac_annual_kwh")
    - source is fully populated
    - assumptions are present (every tool injects at least one default)
    """
    assert result.data, "data must be non-empty"
    for field in result.data:
        prefixes = (f"{field}.", f"{field}[].")
        covered = field in result.units or any(u.startswith(prefixes) for u in result.units)
        assert covered, f"data field {field!r} has no units entry"
    assert result.source.name
    assert result.source.url
    assert result.source.retrieved_at
    assert result.source.license
    assert result.assumptions, "defaults were injected but assumptions is empty"
