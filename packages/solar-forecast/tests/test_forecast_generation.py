import pytest
from solar_mcp_core.errors import BadInput
from solar_mcp_forecast.predictor import ForecastPoint, ForecastRequest
from solar_mcp_forecast.tools.forecast_generation import (
    forecast_generation,
    resolve_forecast_request,
)

from conftest import assert_envelope


def stub_predictor(request: ForecastRequest) -> list[ForecastPoint]:
    """Deterministic hourly ramp: 0, 2, 1 kW then zeros to the horizon."""
    shape = [0.0, 2.0, 1.0]
    points = []
    for hour in range(request.horizon_hours):
        power = shape[hour] if hour < len(shape) else 0.0
        points.append(ForecastPoint(time=f"2026-07-05T{hour:02d}:00:00Z", power_kw=power))
    return points


class TestResolveForecastRequest:
    def test_defaults_are_recorded(self) -> None:
        request, assumptions, _warnings = resolve_forecast_request(
            lat=39.74,
            lon=-105.18,
            capacity_kw=6.0,
            tilt_deg=None,
            azimuth_deg=None,
            horizon_hours=None,
        )
        assert request.tilt_deg == pytest.approx(39.74)
        assert request.azimuth_deg == 180.0
        assert request.horizon_hours == 48
        text = " ".join(assumptions)
        for expected in ("tilt_deg", "azimuth_deg", "horizon_hours"):
            assert expected in text

    def test_explicit_values_produce_no_assumptions(self) -> None:
        _, assumptions, _warnings = resolve_forecast_request(
            lat=39.74,
            lon=-105.18,
            capacity_kw=6.0,
            tilt_deg=25.0,
            azimuth_deg=180.0,
            horizon_hours=24,
        )
        assert assumptions == []

    @pytest.mark.parametrize(
        ("field", "kwargs"),
        [
            ("lat", {"lat": 91.0}),
            ("capacity_kw", {"capacity_kw": 0.01}),
            ("tilt_deg", {"tilt_deg": 95.0}),
            ("azimuth_deg", {"azimuth_deg": 360.0}),
            ("horizon_hours", {"horizon_hours": 49}),
            ("horizon_hours", {"horizon_hours": 0}),
        ],
    )
    def test_out_of_range_rejected(self, field: str, kwargs: dict[str, float]) -> None:
        base: dict[str, object] = {
            "lat": 39.74,
            "lon": -105.18,
            "capacity_kw": 6.0,
            "tilt_deg": 25.0,
            "azimuth_deg": 180.0,
            "horizon_hours": 24,
        }
        base.update(kwargs)
        with pytest.raises(BadInput) as excinfo:
            resolve_forecast_request(**base)  # type: ignore[arg-type]
        assert excinfo.value.field == field


@pytest.mark.anyio
async def test_forecast_generation_totals_and_peak() -> None:
    result = await forecast_generation(
        stub_predictor, lat=39.74, lon=-105.18, capacity_kw=6.0, horizon_hours=6
    )
    assert_envelope(result)
    assert result.data["total_kwh"] == pytest.approx(3.0)  # 0 + 2 + 1 kW over hourly steps
    assert result.data["peak_kw"] == pytest.approx(2.0)
    assert result.data["peak_time"] == "2026-07-05T01:00:00Z"
    assert len(result.data["series"]) == 6
    assert any("Open-source ML forecast" in w for w in result.warnings)
    assert result.source.name.startswith("Quartz")


@pytest.mark.anyio
async def test_predictor_crash_maps_to_source_unavailable() -> None:
    from solar_mcp_core.errors import SourceUnavailable

    def broken(request: ForecastRequest) -> list[ForecastPoint]:
        raise RuntimeError("open-meteo download failed")

    with pytest.raises(SourceUnavailable, match="RuntimeError"):
        await forecast_generation(broken, lat=39.74, lon=-105.18, capacity_kw=6.0)


@pytest.mark.anyio
async def test_shortfall_hours_are_reported() -> None:
    def short(request: ForecastRequest) -> list[ForecastPoint]:
        return [ForecastPoint(time="2026-07-05T00:00:00Z", power_kw=1.0)]

    result = await forecast_generation(
        short, lat=39.74, lon=-105.18, capacity_kw=6.0, horizon_hours=24
    )
    assert result.data["hours_returned"] == 1
    assert any("1 of 24 requested hours" in w for w in result.warnings)
