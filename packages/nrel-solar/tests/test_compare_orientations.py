import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from solar_mcp_core.config import NREL
from solar_mcp_core.errors import BadInput, SourceUnavailable
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_nrel.models import SystemSpec
from solar_mcp_nrel.tools.compare_orientations import (
    MAX_COMBINATIONS,
    compare_orientations,
    rank_grid,
    validate_grid,
)

from conftest import RoutedTransport, assert_envelope, build_client

BOULDER = SystemSpec(lat=39.74, lon=-105.18)


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

    def test_out_of_range_values_rejected_with_index(self) -> None:
        with pytest.raises(BadInput) as excinfo:
            validate_grid([10, 95], [180])
        assert excinfo.value.field == "tilts[1]"
        with pytest.raises(BadInput) as excinfo:
            validate_grid([10], [180, 360])
        assert excinfo.value.field == "azimuths[1]"


class TestRankGrid:
    def cells(self) -> list[dict[str, Any]]:
        return [
            {"tilt_deg": 10, "azimuth_deg": 180, "ac_annual_kwh": 900.0},
            {"tilt_deg": 25, "azimuth_deg": 180, "ac_annual_kwh": 1000.0},
            {"tilt_deg": 25, "azimuth_deg": 90, "ac_annual_kwh": 800.0},
        ]

    def test_best_first_with_zero_delta(self) -> None:
        ranked = rank_grid(self.cells())
        assert ranked[0]["tilt_deg"] == 25 and ranked[0]["azimuth_deg"] == 180
        assert ranked[0]["pct_delta_vs_best"] == 0.0

    def test_deltas_are_percent_vs_best(self) -> None:
        ranked = rank_grid(self.cells())
        assert ranked[1]["pct_delta_vs_best"] == -10.0
        assert ranked[2]["pct_delta_vs_best"] == -20.0

    def test_empty_grid_ranks_empty(self) -> None:
        assert rank_grid([]) == []


@pytest.mark.anyio
async def test_compare_orientations_replay(nrel_client: SolarHttpClient) -> None:
    result = await compare_orientations(
        nrel_client,
        BOULDER,
        4.0,
        tilts=[10.0, 25.0],
        azimuths=[135.0, 180.0, 225.0],
    )
    assert_envelope(result)
    assert result.data["best"] == {"tilt_deg": 25.0, "azimuth_deg": 180.0}
    ranked = result.data["ranked"]
    assert len(ranked) == 6
    assert ranked[0]["pct_delta_vs_best"] == 0.0
    deltas = [cell["pct_delta_vs_best"] for cell in ranked]
    assert deltas == sorted(deltas, reverse=True)  # ranked best -> worst
    assert any("PVWatts models a typical system" in w for w in result.warnings)


def routed_client(tmp_path: Path, handler: Any) -> SolarHttpClient:
    return build_client(NREL, handler, tmp_path)


def ok_body(ac_annual: float) -> dict[str, Any]:
    return {
        "errors": [],
        "warnings": [],
        "station_info": {"lat": 40.0, "lon": -105.2},
        "outputs": {
            "ac_annual": ac_annual,
            "ac_monthly": [ac_annual / 12] * 12,
            "solrad_annual": 4.8,
            "capacity_factor": 18.0,
        },
    }


@pytest.mark.anyio
async def test_partial_failure_returns_ranked_survivors_with_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NREL_API_KEY", "TESTKEY")

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params["tilt"] == "10.0":  # this orientation's weather cell is "down"
            return httpx.Response(500)
        return httpx.Response(200, json=ok_body(ac_annual=1000 * float(params["tilt"])))

    client = routed_client(tmp_path, handler)
    result = await compare_orientations(
        client, BOULDER, 4.0, tilts=[10.0, 25.0], azimuths=[135.0, 180.0]
    )
    assert len(result.data["ranked"]) == 2  # the two tilt=25 cells survived
    assert any("partial result: 2 of 4 combinations failed" in w for w in result.warnings)


@pytest.mark.anyio
async def test_quota_exhaustion_short_circuits_the_sweep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After the first 429, untried combinations must not burn the rolling window."""
    monkeypatch.setenv("NREL_API_KEY", "TESTKEY")
    transport = RoutedTransport(lambda request: httpx.Response(429))
    client = build_client(NREL, transport, tmp_path)

    with pytest.raises(SourceUnavailable, match="orientation combinations failed"):
        await compare_orientations(
            client, BOULDER, 4.0, tilts=[10.0, 25.0, 40.0], azimuths=[135.0, 180.0, 225.0]
        )
    # 9 combinations requested, but at most the first concurrent batch hit the API.
    assert len(transport.requests) <= 4


@pytest.mark.anyio
async def test_cell_warnings_are_aggregated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NREL_API_KEY", "TESTKEY")

    def handler(request: httpx.Request) -> httpx.Response:
        body = ok_body(ac_annual=6000.0)
        body["station_info"]["distance"] = 45_000  # far weather cell for every orientation
        return httpx.Response(200, json=json.loads(json.dumps(body)))

    client = routed_client(tmp_path, handler)
    result = await compare_orientations(client, BOULDER, 4.0, tilts=[10.0], azimuths=[180.0])
    assert any("45 km" in w for w in result.warnings)
