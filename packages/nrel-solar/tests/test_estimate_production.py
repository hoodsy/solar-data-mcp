from pathlib import Path
from typing import Any

import httpx
import pytest
from solar_mcp_core.cache import HttpCache
from solar_mcp_core.config import NREL
from solar_mcp_core.errors import BadInput
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_core.ratelimit import TokenBucket
from solar_mcp_nrel.models import SystemSpec
from solar_mcp_nrel.tools.estimate_production import estimate_production, resolve_request

from conftest import FakeTime, ScriptedTransport, assert_envelope

BOULDER_LAT = 39.74
BOULDER_LON = -105.18


def boulder_spec(**overrides: Any) -> SystemSpec:
    return SystemSpec(lat=BOULDER_LAT, lon=BOULDER_LON, **overrides)


def pvwatts_body(**station_overrides: Any) -> dict[str, Any]:
    """Minimal valid PVWatts response for transport-scripted tool tests."""
    station = {"lat": 40.0, "lon": -105.2, **station_overrides}
    return {
        "errors": [],
        "warnings": [],
        "station_info": station,
        "outputs": {
            "ac_annual": 6500.0,
            "ac_monthly": [500.0] * 12,
            "solrad_annual": 4.8,
            "capacity_factor": 18.5,
        },
    }


def scripted_client(
    tmp_path: Path, fake: FakeTime, responses: list[httpx.Response | Exception]
) -> SolarHttpClient:
    return SolarHttpClient(
        NREL,
        transport=ScriptedTransport(responses),
        cache=HttpCache(path=tmp_path / "http.db", clock=fake.clock),
        bucket=TokenBucket.per_hour(1000, clock=fake.clock, sleep=fake.sleep),
        sleep=fake.sleep,
    )


class TestResolveRequest:
    def test_tilt_defaults_to_latitude_with_assumption(self) -> None:
        resolved = resolve_request(boulder_spec(), 4.0)
        assert resolved.request.tilt == pytest.approx(39.74)
        assert any("tilt_deg not provided" in a and "39.7" in a for a in resolved.assumptions)

    def test_every_injected_default_is_stated(self) -> None:
        resolved = resolve_request(boulder_spec(), 4.0)
        text = " ".join(resolved.assumptions)
        for expected in (
            "tilt_deg",
            "azimuth_deg",
            "array_type",
            "module_type",
            "losses_pct",
            "dc_ac_ratio",
            "dataset=nsrdb",
        ):
            assert expected in text, f"assumption missing for {expected}"

    def test_explicit_values_are_not_reported_as_assumptions(self) -> None:
        spec = boulder_spec(
            tilt_deg=25.0,
            azimuth_deg=180.0,
            array_type="fixed_roof",
            module_type="standard",
            losses_pct=14.0,
            dc_ac_ratio=1.2,
        )
        resolved = resolve_request(spec, 4.0, albedo=0.3)
        # Explicit choices — even ones equal to the defaults — are the
        # caller's, not ours; nothing may be reported as injected.
        injected = [a for a in resolved.assumptions if "not provided" in a or "defaulted" in a]
        assert injected == []

    def test_southern_hemisphere_south_azimuth_warns_even_when_explicit(self) -> None:
        defaulted = resolve_request(SystemSpec(lat=-33.9, lon=151.2), 4.0)
        explicit = resolve_request(SystemSpec(lat=-33.9, lon=151.2, azimuth_deg=180.0), 4.0)
        for resolved in (defaulted, explicit):
            assert any("Southern-hemisphere" in w for w in resolved.warnings)
        assert defaulted.request.tilt == pytest.approx(33.9)  # abs(lat)

    def test_northern_hemisphere_does_not_warn(self) -> None:
        assert resolve_request(boulder_spec(), 4.0).warnings == []

    def test_bifacial_injects_stated_coefficient(self) -> None:
        resolved = resolve_request(boulder_spec(), 4.0, bifacial=True)
        assert resolved.request.bifaciality == 0.7
        assert any("bifaciality coefficient assumed 0.7" in a for a in resolved.assumptions)

    def test_non_bifacial_sends_no_coefficient(self) -> None:
        assert resolve_request(boulder_spec(), 4.0).request.bifaciality is None


@pytest.mark.anyio
async def test_estimate_production_boulder(nrel_client: SolarHttpClient) -> None:
    result = await estimate_production(nrel_client, boulder_spec(tilt_deg=25.0), 4.0)
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
    result = await estimate_production(nrel_client, boulder_spec(), 4.0)
    assert_envelope(result)
    assert any("defaulted to site latitude" in a for a in result.assumptions)


@pytest.mark.anyio
async def test_estimate_production_rejects_bad_tilt(nrel_client: SolarHttpClient) -> None:
    with pytest.raises(BadInput, match="tilt"):
        await estimate_production(nrel_client, boulder_spec(tilt_deg=95.0), 4.0)


@pytest.mark.anyio
async def test_stale_cache_serve_is_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quota exhausted + expired cache entry -> result carries a staleness warning."""
    monkeypatch.setenv("NREL_API_KEY", "TESTKEY")
    fake = FakeTime()
    client = scripted_client(
        tmp_path, fake, [httpx.Response(200, json=pvwatts_body()), httpx.Response(429)]
    )
    spec = boulder_spec(tilt_deg=25.0)

    fresh = await estimate_production(client, spec, 4.0)
    assert not any("expired cache" in w for w in fresh.warnings)

    fake.now += NREL.cache_ttl_seconds + 1
    stale = await estimate_production(client, spec, 4.0)
    assert any("expired cache" in w for w in stale.warnings)
    assert stale.data["ac_annual_kwh"] == fresh.data["ac_annual_kwh"]


@pytest.mark.anyio
async def test_far_station_produces_distance_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NREL_API_KEY", "TESTKEY")
    fake = FakeTime()
    client = scripted_client(
        tmp_path, fake, [httpx.Response(200, json=pvwatts_body(distance=45_000))]
    )

    result = await estimate_production(client, boulder_spec(tilt_deg=25.0), 4.0)
    assert any("45 km" in w for w in result.warnings)
