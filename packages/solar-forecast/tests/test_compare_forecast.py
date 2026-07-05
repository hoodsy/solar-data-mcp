import calendar
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from solar_mcp_core.config import NREL
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_forecast.predictor import ForecastPoint, ForecastRequest, Predictor
from solar_mcp_forecast.tools.compare_forecast_to_model import compare_forecast_to_model

from conftest import assert_envelope, build_client


def flat_predictor(power_kw: float) -> Predictor:
    def predict(request: ForecastRequest) -> list[ForecastPoint]:
        return [
            ForecastPoint(time=f"2026-07-05T{hour:02d}:00:00Z", power_kw=power_kw)
            for hour in range(request.horizon_hours)
        ]

    return predict


def nrel_client_with_flat_months(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SolarHttpClient:
    """PVWatts stub tuned to exactly 1 kWh per hour in every calendar month."""
    monkeypatch.setenv("NREL_API_KEY", "TESTKEY")
    year = datetime.now(tz=UTC).year
    ac_monthly = [calendar.monthrange(year, month)[1] * 24.0 for month in range(1, 13)]
    body = {
        "errors": [],
        "warnings": [],
        "station_info": {"lat": 39.7, "lon": -105.2},
        "outputs": {
            "ac_annual": sum(ac_monthly),
            "ac_monthly": ac_monthly,
            "solrad_annual": 4.8,
            "capacity_factor": 16.4,
        },
    }
    return build_client(NREL, lambda request: httpx.Response(200, json=body), tmp_path)


@pytest.mark.anyio
async def test_sunny_forecast_flagged_above_typical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = nrel_client_with_flat_months(tmp_path, monkeypatch)
    result = await compare_forecast_to_model(
        flat_predictor(1.25), client, lat=39.74, lon=-105.18, capacity_kw=6.0, horizon_hours=24
    )
    assert_envelope(result)
    assert result.data["tmy_expected_kwh"] == pytest.approx(24.0)
    assert result.data["forecast_kwh"] == pytest.approx(30.0)
    assert result.data["ratio_pct"] == pytest.approx(125.0)
    assert "unusually sunny" in result.data["verdict"]
    assert not any("not a whole number of days" in w for w in result.warnings)


@pytest.mark.anyio
async def test_cloudy_forecast_flagged_below_typical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = nrel_client_with_flat_months(tmp_path, monkeypatch)
    result = await compare_forecast_to_model(
        flat_predictor(0.5), client, lat=39.74, lon=-105.18, capacity_kw=6.0, horizon_hours=24
    )
    assert result.data["ratio_pct"] == pytest.approx(50.0)
    assert "below typical" in result.data["verdict"]


@pytest.mark.anyio
async def test_partial_day_horizon_warns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = nrel_client_with_flat_months(tmp_path, monkeypatch)
    result = await compare_forecast_to_model(
        flat_predictor(1.0), client, lat=39.74, lon=-105.18, capacity_kw=6.0, horizon_hours=30
    )
    assert any("not a whole number of days" in w for w in result.warnings)
    assert any("uniformly" in a for a in result.assumptions)
