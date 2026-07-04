from typing import Any

import pytest
from helpers import assert_envelope
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_nrel.tools.estimate_production import estimate_production, resolve_request

BOULDER: dict[str, float] = {"lat": 39.74, "lon": -105.18}
BOULDER_LAT = 39.74
BOULDER_LON = -105.18


def resolve(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        **BOULDER,
        "system_capacity_kw": 4.0,
        "tilt_deg": None,
        "azimuth_deg": 180.0,
        "array_type": "fixed_roof",
        "module_type": "standard",
        "losses_pct": 14.0,
        "bifacial": False,
        "albedo": None,
        "dc_ac_ratio": 1.2,
    }
    return resolve_request(**{**base, **overrides})


class TestResolveRequest:
    def test_tilt_defaults_to_latitude_with_assumption(self) -> None:
        resolved = resolve()
        assert resolved.request.tilt == pytest.approx(39.74)
        assert any("tilt_deg not provided" in a and "39.7" in a for a in resolved.assumptions)

    def test_explicit_tilt_produces_no_tilt_assumption(self) -> None:
        resolved = resolve(tilt_deg=25.0)
        assert resolved.request.tilt == 25.0
        assert not any("tilt_deg" in a for a in resolved.assumptions)

    def test_every_spec_default_is_stated(self) -> None:
        resolved = resolve()
        text = " ".join(resolved.assumptions)
        for expected in (
            "azimuth_deg=180",
            "fixed_roof",
            "standard",
            "losses_pct=14.0",
            "dc_ac_ratio=1.2",
            "dataset=nsrdb",
        ):
            assert expected in text, f"assumption missing for {expected}"

    def test_southern_hemisphere_default_azimuth_warns(self) -> None:
        resolved = resolve(lat=-33.9, lon=151.2)
        assert any("Southern-hemisphere" in w for w in resolved.warnings)
        assert resolved.request.tilt == pytest.approx(33.9)  # abs(lat)

    def test_northern_hemisphere_does_not_warn(self) -> None:
        assert resolve().warnings == []

    def test_bifacial_injects_stated_coefficient(self) -> None:
        resolved = resolve(bifacial=True)
        assert resolved.request.bifaciality == 0.7
        assert any("bifaciality coefficient assumed 0.7" in a for a in resolved.assumptions)

    def test_non_bifacial_sends_no_coefficient(self) -> None:
        assert resolve().request.bifaciality is None


@pytest.mark.anyio
async def test_estimate_production_boulder(nrel_client: SolarHttpClient) -> None:
    result = await estimate_production(
        nrel_client, lat=BOULDER_LAT, lon=BOULDER_LON, system_capacity_kw=4.0, tilt_deg=25.0
    )
    assert_envelope(result)
    assert result.data["ac_annual_kwh"] > 4000  # 4 kW in Colorado clears 1000 kWh/kW
    assert len(result.data["ac_monthly"]) == 12
    assert 0 < result.data["capacity_factor"] < 100  # percent, not fraction
    assert result.units["capacity_factor"] == "%"
    assert any("PVWatts models a typical system" in w for w in result.warnings)
    assert result.source.name == "NREL PVWatts v8"
    assert "api_key" not in result.source.url


@pytest.mark.anyio
async def test_estimate_production_default_tilt_end_to_end(
    nrel_client: SolarHttpClient,
) -> None:
    result = await estimate_production(
        nrel_client, lat=BOULDER_LAT, lon=BOULDER_LON, system_capacity_kw=4.0
    )
    assert_envelope(result)
    assert any("defaulted to site latitude" in a for a in result.assumptions)


@pytest.mark.anyio
async def test_estimate_production_rejects_bad_tilt(nrel_client: SolarHttpClient) -> None:
    from solar_mcp_core.errors import BadInput

    with pytest.raises(BadInput, match="tilt"):
        await estimate_production(
            nrel_client, lat=BOULDER_LAT, lon=BOULDER_LON, system_capacity_kw=4.0, tilt_deg=95.0
        )
