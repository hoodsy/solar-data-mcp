from solar_mcp_core.envelope import SourceRef, ToolResult


def make_result() -> ToolResult:
    return ToolResult(
        data={"ac_annual_kwh": 6543.2},
        units={"ac_annual_kwh": "kWh_ac"},
        source=SourceRef(
            name="NREL PVWatts v8",
            url="https://developer.nrel.gov/api/pvwatts/v8.json?lat=33.4&lon=-111.8",
            retrieved_at="2026-07-05T00:00:00Z",
            license="NREL Developer Network",
        ),
        assumptions=["tilt_deg not provided; defaulted to site latitude 33.4"],
        warnings=[],
    )


def test_round_trips_through_model_dump() -> None:
    result = make_result()
    restored = ToolResult.model_validate(result.model_dump())
    assert restored == result


def test_lists_default_to_empty() -> None:
    result = ToolResult(
        data={"x": 1},
        source=SourceRef(name="n", url="u", retrieved_at="t", license="l"),
    )
    assert result.assumptions == []
    assert result.warnings == []
    assert result.units == {}
