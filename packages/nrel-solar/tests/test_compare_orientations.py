from typing import Any

import pytest
from helpers import assert_envelope
from solar_mcp_core.errors import BadInput
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_nrel.tools.compare_orientations import (
    MAX_COMBINATIONS,
    rank_grid,
    validate_grid,
)


class TestValidateGrid:
    def test_default_sized_grid_allowed(self) -> None:
        validate_grid([0, 10, 20, 30, 40], [90, 135, 180, 225, 270])  # exactly 25

    def test_oversized_grid_rejected_before_http(self) -> None:
        with pytest.raises(BadInput) as excinfo:
            validate_grid([0, 10, 20, 30, 40, 50], [90, 135, 180, 225, 270])
        assert str(MAX_COMBINATIONS) in str(excinfo.value)
        assert "6x5=30" in str(excinfo.value)

    def test_empty_grid_rejected(self) -> None:
        with pytest.raises(BadInput):
            validate_grid([], [180])


class TestRankGrid:
    def cells(self) -> list[dict[str, Any]]:
        return [
            {"tilt": 10, "azimuth": 180, "ac_annual_kwh": 900.0},
            {"tilt": 25, "azimuth": 180, "ac_annual_kwh": 1000.0},
            {"tilt": 25, "azimuth": 90, "ac_annual_kwh": 800.0},
        ]

    def test_best_first_with_zero_delta(self) -> None:
        ranked = rank_grid(self.cells())
        assert ranked[0]["tilt"] == 25 and ranked[0]["azimuth"] == 180
        assert ranked[0]["pct_delta_vs_best"] == 0.0

    def test_deltas_are_percent_vs_best(self) -> None:
        ranked = rank_grid(self.cells())
        assert ranked[1]["pct_delta_vs_best"] == -10.0
        assert ranked[2]["pct_delta_vs_best"] == -20.0

    def test_empty_grid_ranks_empty(self) -> None:
        assert rank_grid([]) == []


@pytest.mark.anyio
async def test_compare_orientations_replay(nrel_client: SolarHttpClient) -> None:
    from solar_mcp_nrel.tools.compare_orientations import compare_orientations

    result = await compare_orientations(
        nrel_client,
        lat=39.74,
        lon=-105.18,
        system_capacity_kw=4.0,
        tilts=[10.0, 25.0],
        azimuths=[135.0, 180.0, 225.0],
    )
    assert_envelope(result)
    assert result.data["best"] == {"tilt": 25.0, "azimuth": 180.0}
    ranked = result.data["ranked"]
    assert len(ranked) == 6
    assert ranked[0]["pct_delta_vs_best"] == 0.0
    assert all(cell["pct_delta_vs_best"] <= 0 for cell in ranked)
    deltas = [cell["pct_delta_vs_best"] for cell in ranked]
    assert deltas == sorted(deltas, reverse=True)  # ranked best -> worst
