"""Hand-computed cases for the pure financial math — no mocks, no I/O."""

import pytest
from solar_mcp_economics.economics import (
    YearRow,
    cash_flow_table,
    irr_pct,
    itc_rate,
    npv,
    simple_payback_years,
)


def flat_rows(savings_per_year: float, years: int = 25) -> list[YearRow]:
    return cash_flow_table(
        annual_production_kwh=savings_per_year * 10,  # rate 0.1 -> savings as given
        rate_usd_per_kwh=0.1,
        escalation_pct=0.0,
        degradation_pct=0.0,
        years=years,
    )


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (2021, 0.26),
        (2022, 0.30),
        (2026, 0.30),
        (2032, 0.30),
        (2033, 0.26),
        (2034, 0.22),
        (2035, 0.0),
    ],
)
def test_itc_schedule(year: int, expected: float) -> None:
    assert itc_rate(year) == expected


def test_flat_cash_flow_hand_case() -> None:
    rows = flat_rows(1000.0)
    assert rows[0].savings_usd == pytest.approx(1000.0)
    assert rows[-1].cumulative_usd == pytest.approx(25_000.0)


def test_degradation_compounds() -> None:
    rows = cash_flow_table(
        annual_production_kwh=1000,
        rate_usd_per_kwh=0.1,
        escalation_pct=0.0,
        degradation_pct=0.5,
        years=2,
    )
    assert rows[0].production_kwh == pytest.approx(1000.0)
    assert rows[1].production_kwh == pytest.approx(995.0)


def test_escalation_compounds() -> None:
    rows = cash_flow_table(
        annual_production_kwh=1000,
        rate_usd_per_kwh=0.10,
        escalation_pct=10.0,
        degradation_pct=0.0,
        years=2,
    )
    assert rows[1].rate_usd_per_kwh == pytest.approx(0.11)


def test_payback_interpolates_within_the_crossing_year() -> None:
    rows = flat_rows(1000.0)
    assert simple_payback_years(10_000, rows) == pytest.approx(10.0)
    assert simple_payback_years(2_500, rows) == pytest.approx(2.5)
    assert simple_payback_years(10_000_000, rows) is None


def test_npv_at_zero_discount_is_sum_minus_cost() -> None:
    rows = flat_rows(1000.0)
    assert npv(0.0, 10_000, rows) == pytest.approx(15_000.0)
    assert npv(6.0, 10_000, rows) < 15_000.0  # discounting only reduces it


def test_irr_exact_zero_case() -> None:
    # -10,000 now, +5,000 in each of two years: NPV = 0 exactly at r = 0.
    rows = flat_rows(5000.0, years=2)
    assert irr_pct(10_000, rows) == pytest.approx(0.0, abs=0.01)


def test_irr_none_when_cost_unrecoverable() -> None:
    rows = flat_rows(1.0, years=2)
    assert irr_pct(10_000, rows) is None


def test_irr_known_annuity_value() -> None:
    # 25-year annuity of 1,000 against 10,000: annuity factor 10 -> IRR ~ 8.78%.
    rows = flat_rows(1000.0)
    result = irr_pct(10_000, rows)
    assert result is not None
    assert result == pytest.approx(8.78, abs=0.05)
