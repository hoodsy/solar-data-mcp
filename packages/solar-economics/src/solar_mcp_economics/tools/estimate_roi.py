"""estimate_roi: the composite — production x tariffs x incentives -> cash flow.

Chains Phase 1's estimate_production (imported as a library, never MCP-to-MCP),
lookup_tariffs, and the incentives table into an auditable screening estimate.
Every number in the output can be traced: the audit_trail lists each component's
source, and the assumptions section lists every default and simplification.
"""

from dataclasses import asdict
from datetime import UTC, datetime

from solar_mcp_core import units
from solar_mcp_core.bulk import BulkStore
from solar_mcp_core.envelope import SourceRef, ToolResult
from solar_mcp_core.errors import BadInput, SolarMCPError, SourceUnavailable
from solar_mcp_core.http import SolarHttpClient
from solar_mcp_nrel.models import SystemSpec
from solar_mcp_nrel.tools.estimate_production import estimate_production

from solar_mcp_economics import economics
from solar_mcp_economics.incentives import federal_incentives
from solar_mcp_economics.models import validate_state
from solar_mcp_economics.tools.get_electricity_prices import get_electricity_prices
from solar_mcp_economics.tools.lookup_tariffs import lookup_tariffs

SCREENING_CAVEAT = (
    "Screening estimate; not a substitute for a site-specific proposal. "
    "Financing, roof condition, shading, rate riders, and export compensation "
    "rules are not modeled."
)
# Fallback when the user gives no cost and no Tracking the Sun snapshot is synced.
NATIONAL_MEDIAN_COST_PER_WATT = 3.0
NATIONAL_MEDIAN_CITATION = (
    "LBNL Tracking the Sun 2024 — national median residential installed price"
)
DEFAULT_ESCALATION_PCT = 2.5
DEFAULT_DISCOUNT_RATE_PCT = 6.0

# Phase 3's sync_tracking_the_sun fills this table; until then the national
# median constant above is the fallback.
TTS_TABLE = "tts_systems"


async def estimate_roi(
    nrel_client: SolarHttpClient,
    openei_client: SolarHttpClient,
    eia_client: SolarHttpClient,
    store: BulkStore,
    *,
    lat: float,
    lon: float,
    system_capacity_kw: float,
    state: str | None = None,
    install_cost_usd: float | None = None,
    cost_per_watt: float | None = None,
    annual_consumption_kwh: float | None = None,
    escalation_pct: float | None = None,
    discount_rate_pct: float | None = None,
    install_year: int | None = None,
) -> ToolResult:
    assumptions: list[str] = []
    warnings: list[str] = [SCREENING_CAVEAT]
    audit: list[dict[str, str]] = []

    if install_cost_usd is not None and cost_per_watt is not None:
        raise BadInput(
            field="install_cost_usd/cost_per_watt",
            value=f"{install_cost_usd}/{cost_per_watt}",
            allowed="at most one of install_cost_usd or cost_per_watt",
        )
    if state is not None:
        state = validate_state(state)
    if escalation_pct is None:
        escalation_pct = DEFAULT_ESCALATION_PCT
        assumptions.append(f"escalation_pct not provided; assumed {escalation_pct}%/yr")
    if discount_rate_pct is None:
        discount_rate_pct = DEFAULT_DISCOUNT_RATE_PCT
        assumptions.append(f"discount_rate_pct not provided; assumed {discount_rate_pct}%")
    if install_year is None:
        install_year = datetime.now(tz=UTC).year
        assumptions.append(f"install_year not provided; assumed {install_year}")

    # 1. Production (Phase 1, as a library).
    production = await estimate_production(
        nrel_client, SystemSpec(lat=lat, lon=lon), system_capacity_kw
    )
    annual_kwh = float(production.data["ac_annual_kwh"])
    audit.append(_component("production", production.source))
    assumptions.extend(f"production: {line}" for line in production.assumptions)

    # 2. Electricity rate: URDB flat/tiered tariff first, EIA state average fallback.
    rate_usd_per_kwh, rate_lines, rate_warnings = await _resolve_rate(
        openei_client, eia_client, lat=lat, lon=lon, state=state, audit=audit
    )
    assumptions.extend(rate_lines)
    warnings.extend(rate_warnings)

    # 3. Costs and the federal ITC.
    gross_cost, cost_lines = _resolve_cost(
        store, system_capacity_kw, install_cost_usd, cost_per_watt, state, audit
    )
    assumptions.extend(cost_lines)
    itc = economics.itc_rate(install_year)
    itc_usd = round(gross_cost * itc, 2)
    net_cost = round(gross_cost - itc_usd, 2)
    assumptions.append(
        f"federal ITC {itc:.0%} netted against cost ({economics.ITC_CITATION}); "
        "state/local incentives are listed by get_incentives but not netted "
        "(value formulas vary)"
    )

    # 4. Cash flow and summary metrics.
    assumptions.append(
        f"panel degradation {economics.DEFAULT_DEGRADATION_PCT}%/yr; savings assume "
        "full retail credit for all production (net metering)"
    )
    rows = economics.cash_flow_table(
        annual_production_kwh=annual_kwh,
        rate_usd_per_kwh=rate_usd_per_kwh,
        escalation_pct=escalation_pct,
    )
    payback = economics.simple_payback_years(net_cost, rows)
    if payback is None:
        warnings.append(
            f"savings do not recover the net cost within {economics.ANALYSIS_YEARS} years"
        )
    if annual_consumption_kwh is not None and annual_kwh > annual_consumption_kwh:
        warnings.append(
            f"year-1 production ({annual_kwh:.0f} kWh) exceeds stated consumption "
            f"({annual_consumption_kwh:.0f} kWh); export compensation varies and full "
            "retail credit may overstate savings"
        )

    federal = federal_incentives(install_year)
    return ToolResult(
        data={
            "payback_years": payback,
            "npv_usd": economics.npv(discount_rate_pct, net_cost, rows),
            "irr_pct": economics.irr_pct(net_cost, rows),
            "year1_savings_usd": rows[0].savings_usd,
            "annual_production_kwh_year1": round(annual_kwh, 1),
            "effective_rate_usd_per_kwh": round(rate_usd_per_kwh, 4),
            "gross_cost_usd": round(gross_cost, 2),
            "itc_usd": itc_usd,
            "net_cost_usd": net_cost,
            "federal_incentives": [item.model_dump() for item in federal],
            "cash_flow": [asdict(row) for row in rows],
            "audit_trail": audit,
        },
        units={
            "payback_years": units.YEARS,
            "npv_usd": units.USD,
            "irr_pct": units.PERCENT,
            "year1_savings_usd": units.USD,
            "annual_production_kwh_year1": units.KWH_AC_PER_YEAR,
            "effective_rate_usd_per_kwh": units.USD_PER_KWH,
            "gross_cost_usd": units.USD,
            "itc_usd": units.USD,
            "net_cost_usd": units.USD,
            "federal_incentives[].value": units.LABEL,
            "cash_flow[].production_kwh": units.KWH,
            "cash_flow[].rate_usd_per_kwh": units.USD_PER_KWH,
            "cash_flow[].savings_usd": units.USD,
            "cash_flow[].cumulative_usd": units.USD,
            "audit_trail[].component": units.LABEL,
            "audit_trail[].retrieved_at": units.ISO_DATE,
        },
        source=SourceRef(
            name="solar-data-mcp composite (see audit_trail)",
            url="https://github.com/loganbernard/solar-data-mcp",
            retrieved_at=datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            license="components individually licensed; see audit_trail",
        ),
        assumptions=assumptions,
        warnings=warnings,
    )


async def _resolve_rate(
    openei_client: SolarHttpClient,
    eia_client: SolarHttpClient,
    *,
    lat: float,
    lon: float,
    state: str | None,
    audit: list[dict[str, str]],
) -> tuple[float, list[str], list[str]]:
    try:
        tariffs = await lookup_tariffs(openei_client, lat=lat, lon=lon)
        for tariff in tariffs.data["tariffs"]:
            rate = tariff["first_tier_rate_usd_per_kwh"]
            if not tariff["is_tou"] and rate:
                audit.append(_component("electricity_rate", tariffs.source))
                return (
                    float(rate),
                    [
                        f"electricity rate from URDB tariff {tariff['name']!r} "
                        f"({tariff['utility']}), tier 1"
                    ],
                    [],
                )
        failure = "URDB returned only time-of-use schedules"
    except SolarMCPError as exc:
        failure = f"URDB lookup failed ({exc})"

    if state is None:
        raise SourceUnavailable(
            "openei",
            failure + "; pass state=XX to fall back to the EIA state-average rate",
        )
    prices = await get_electricity_prices(eia_client, state=state)
    audit.append(_component("electricity_rate", prices.source))
    rate = float(prices.data["latest_price_cents_per_kwh"]) / 100
    return (
        rate,
        [f"electricity rate is the EIA {state} residential average"],
        [f"{failure}; using the EIA state average instead of an actual tariff"],
    )


def _resolve_cost(
    store: BulkStore,
    system_capacity_kw: float,
    install_cost_usd: float | None,
    cost_per_watt: float | None,
    state: str | None,
    audit: list[dict[str, str]],
) -> tuple[float, list[str]]:
    watts = system_capacity_kw * 1000
    if install_cost_usd is not None:
        if install_cost_usd <= 0:
            raise BadInput(field="install_cost_usd", value=install_cost_usd, allowed="> 0")
        audit.append(_user_component("install_cost"))
        return install_cost_usd, []
    if cost_per_watt is not None:
        if cost_per_watt <= 0:
            raise BadInput(field="cost_per_watt", value=cost_per_watt, allowed="> 0")
        audit.append(_user_component("install_cost"))
        return cost_per_watt * watts, [f"install cost = {cost_per_watt} $/W x system size"]

    if state is not None and store.has_table(TTS_TABLE):
        rows = store.query(
            f"SELECT median(price_per_watt), count(*) FROM {TTS_TABLE} WHERE upper(state) = ?",
            [state],
        )
        median, count = rows[0] if rows else (None, 0)
        if median is not None and count:
            vintage = store.vintage("tts")
            audit.append(
                {
                    "component": "install_cost",
                    "source": "LBNL Tracking the Sun (local snapshot)",
                    "url": "https://emp.lbl.gov/tracking-the-sun",
                    "retrieved_at": vintage.loaded_at if vintage else "unknown",
                }
            )
            return (
                float(median) * watts,
                [
                    f"install cost not provided; using {state} median "
                    f"{float(median):.2f} $/W from Tracking the Sun snapshot "
                    f"({count} systems)"
                ],
            )

    audit.append(
        {
            "component": "install_cost",
            "source": NATIONAL_MEDIAN_CITATION,
            "url": "https://emp.lbl.gov/tracking-the-sun",
            "retrieved_at": "static constant",
        }
    )
    return (
        NATIONAL_MEDIAN_COST_PER_WATT * watts,
        [
            f"install cost not provided; assumed national median "
            f"{NATIONAL_MEDIAN_COST_PER_WATT} $/W ({NATIONAL_MEDIAN_CITATION})"
        ],
    )


def _component(component: str, source: SourceRef) -> dict[str, str]:
    return {
        "component": component,
        "source": source.name,
        "url": source.url,
        "retrieved_at": source.retrieved_at,
    }


def _user_component(component: str) -> dict[str, str]:
    return {
        "component": component,
        "source": "user-provided",
        "url": "",
        "retrieved_at": "n/a",
    }
