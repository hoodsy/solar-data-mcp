from typing import Any

import pytest
from solar_mcp_core.errors import BadInput
from solar_mcp_core.validation import validate_state
from solar_mcp_economics.models import normalize_tariff, validate_sector

FLAT_SCHEDULE = [[0] * 24 for _ in range(12)]


def item(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "utility": "Test Utility",
        "name": "Rate X",
        "sector": "Residential",
        "uri": "https://example.org/rate/x",
        "energyratestructure": [[{"rate": 0.12}]],
        "energyweekdayschedule": FLAT_SCHEDULE,
        "energyweekendschedule": FLAT_SCHEDULE,
    }
    base.update(overrides)
    return base


def test_flat_rate_normalizes_clean() -> None:
    tariff = normalize_tariff(item())
    assert tariff is not None
    assert tariff.first_tier_rate == pytest.approx(0.12)
    assert not tariff.is_tou and not tariff.is_seasonal
    assert tariff.notes == []


def test_adjustment_is_added_to_rate() -> None:
    tariff = normalize_tariff(item(energyratestructure=[[{"rate": 0.10, "adj": 0.02}]]))
    assert tariff is not None
    assert tariff.first_tier_rate == pytest.approx(0.12)


def test_tiers_carry_max_usage() -> None:
    tariff = normalize_tariff(
        item(energyratestructure=[[{"rate": 0.10, "max": 500}, {"rate": 0.15}]])
    )
    assert tariff is not None
    assert [t.max_usage_kwh for t in tariff.energy_tiers] == [500.0, None]


def test_tou_detected_from_intraday_variation() -> None:
    tou_schedule = [[0] * 12 + [1] * 12 for _ in range(12)]
    tariff = normalize_tariff(item(energyweekdayschedule=tou_schedule))
    assert tariff is not None
    assert tariff.is_tou
    assert any("time-of-use" in note for note in tariff.notes)


def test_seasonal_detected_from_monthly_variation() -> None:
    seasonal = [[0] * 24] * 6 + [[1] * 24] * 6
    tariff = normalize_tariff(item(energyweekdayschedule=seasonal))
    assert tariff is not None
    assert not tariff.is_tou
    assert tariff.is_seasonal
    assert any("seasonal" in note for note in tariff.notes)


def test_multi_period_structure_noted() -> None:
    tariff = normalize_tariff(item(energyratestructure=[[{"rate": 0.10}], [{"rate": 0.20}]]))
    assert tariff is not None
    assert tariff.first_tier_rate == pytest.approx(0.10)
    assert any("period 1 only" in note for note in tariff.notes)


def test_unconvertible_fixed_charge_noted_not_converted() -> None:
    tariff = normalize_tariff(item(fixedchargefirstmeter=1.5, fixedchargeunits="$/day"))
    assert tariff is not None
    assert tariff.fixed_monthly_charge_usd is None
    assert any("$/day" in note for note in tariff.notes)


def test_monthly_fixed_charge_converted() -> None:
    tariff = normalize_tariff(item(fixedchargefirstmeter=12.0, fixedchargeunits="$/month"))
    assert tariff is not None
    assert tariff.fixed_monthly_charge_usd == 12.0


def test_no_energy_rates_returns_none() -> None:
    assert normalize_tariff(item(energyratestructure=None)) is None


def test_sector_and_state_validation() -> None:
    assert validate_sector("residential") == "residential"
    with pytest.raises(BadInput, match="sector"):
        validate_sector("agricultural")
    assert validate_state("co") == "CO"
    with pytest.raises(BadInput, match="state"):
        validate_state("XX")


def test_null_adj_and_rate_are_tolerated() -> None:
    tariff = normalize_tariff(item(energyratestructure=[[{"rate": 0.10, "adj": None}]]))
    assert tariff is not None
    assert tariff.first_tier_rate == pytest.approx(0.10)
