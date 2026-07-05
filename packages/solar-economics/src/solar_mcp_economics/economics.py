"""Pure financial math for solar ROI. No I/O, no API types — unit-tested
against hand-computed cases.

Simplifications are deliberate v1 choices and every caller surfaces them as
assumptions: savings assume full retail credit for all production (net
metering), nominal-dollar payback, constant annual degradation.
"""

from dataclasses import dataclass

DEFAULT_DEGRADATION_PCT = 0.5  # %/yr, industry-standard panel warranty slope
ANALYSIS_YEARS = 25

# Federal residential clean energy credit, 26 USC §25D (as amended by the
# Inflation Reduction Act of 2022): 30% for systems placed in service
# 2022-2032, 26% in 2033, 22% in 2034, expires for 2035+.
ITC_CITATION = "26 USC §25D (Inflation Reduction Act of 2022)"


def itc_rate(install_year: int) -> float:
    if install_year < 2006:
        return 0.0  # §25D did not exist
    if install_year <= 2019:
        return 0.30
    if install_year <= 2021:
        return 0.26  # pre-IRA phase-down years
    if install_year <= 2032:
        return 0.30
    if install_year == 2033:
        return 0.26
    if install_year == 2034:
        return 0.22
    return 0.0


@dataclass
class YearRow:
    year: int
    production_kwh: float
    rate_usd_per_kwh: float
    savings_usd: float
    cumulative_usd: float


def cash_flow_table(
    *,
    annual_production_kwh: float,
    rate_usd_per_kwh: float,
    escalation_pct: float,
    degradation_pct: float = DEFAULT_DEGRADATION_PCT,
    years: int = ANALYSIS_YEARS,
) -> list[YearRow]:
    rows: list[YearRow] = []
    cumulative = 0.0
    for year in range(1, years + 1):
        production = annual_production_kwh * (1 - degradation_pct / 100) ** (year - 1)
        rate = rate_usd_per_kwh * (1 + escalation_pct / 100) ** (year - 1)
        savings = production * rate
        cumulative += savings
        rows.append(
            YearRow(
                year=year,
                production_kwh=round(production, 1),
                rate_usd_per_kwh=round(rate, 4),
                savings_usd=round(savings, 2),
                cumulative_usd=round(cumulative, 2),
            )
        )
    return rows


def simple_payback_years(net_cost_usd: float, rows: list[YearRow]) -> float | None:
    """First point where cumulative nominal savings cover the net cost,
    interpolated within the crossing year. None if never within the table."""
    previous_cumulative = 0.0
    for row in rows:
        if row.cumulative_usd >= net_cost_usd:
            needed = net_cost_usd - previous_cumulative
            fraction = needed / row.savings_usd if row.savings_usd > 0 else 1.0
            return round(row.year - 1 + fraction, 2)
        previous_cumulative = row.cumulative_usd
    return None


def npv(discount_rate_pct: float, net_cost_usd: float, rows: list[YearRow]) -> float:
    rate = discount_rate_pct / 100
    total = -net_cost_usd
    for row in rows:
        total += row.savings_usd / (1 + rate) ** row.year
    return round(total, 2)


def irr_pct(net_cost_usd: float, rows: list[YearRow]) -> float | None:
    """Internal rate of return via bisection.

    None when total nominal savings never recover the cost — a deeply negative
    mathematical root always exists as the rate approaches -100%, but it is
    meaningless for a go/no-go decision, so we refuse to report one.
    """
    if sum(row.savings_usd for row in rows) < net_cost_usd:
        return None
    lo, hi = -0.99, 10.0

    def f(rate: float) -> float:
        total = -net_cost_usd
        for row in rows:
            total += row.savings_usd / (1 + rate) ** row.year
        return total

    f_lo, f_hi = f(lo), f(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = f(mid)
        if abs(f_mid) < 1e-7:
            break
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return round(((lo + hi) / 2) * 100, 2)
