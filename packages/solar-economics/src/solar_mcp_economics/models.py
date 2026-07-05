"""Models and normalization for the economics sources.

URDB rate schedules are deeply nested (tiers x periods x month-hour
schedules); `normalize_tariff` reduces each to a small flat `Tariff` an agent
can reason about, flagging anything (TOU, seasonal periods) the flat view
approximates. Full TOU simulation is deliberately out of scope for v1.
"""

from typing import Any, Literal, cast

from pydantic import BaseModel, Field
from solar_mcp_core.errors import BadInput

Sector = Literal["residential", "commercial", "industrial"]
DEFAULT_SECTOR: Sector = "residential"

URDB_SECTOR: dict[str, str] = {
    "residential": "Residential",
    "commercial": "Commercial",
    "industrial": "Industrial",
}
EIA_SECTOR: dict[str, str] = {
    "residential": "RES",
    "commercial": "COM",
    "industrial": "IND",
}


def validate_sector(sector: str) -> Sector:
    if sector not in URDB_SECTOR:
        raise BadInput(
            field="sector", value=sector, allowed="one of: residential, commercial, industrial"
        )
    return cast(Sector, sector)


# ---------------------------------------------------------------- URDB


class EnergyTier(BaseModel):
    rate_usd_per_kwh: float
    max_usage_kwh: float | None = None  # None = open-ended top tier


class Tariff(BaseModel):
    """Flat, agent-readable view of one URDB rate schedule."""

    utility: str
    name: str
    sector: str
    energy_tiers: list[EnergyTier]
    fixed_monthly_charge_usd: float | None
    is_tou: bool
    is_seasonal: bool
    uri: str
    source: str | None = None
    notes: list[str] = Field(default_factory=list)

    @property
    def first_tier_rate(self) -> float | None:
        return self.energy_tiers[0].rate_usd_per_kwh if self.energy_tiers else None


class UrdbResponse(BaseModel):
    items: list[dict[str, Any]]


def normalize_tariff(item: dict[str, Any]) -> Tariff | None:
    """Reduce one URDB item to a Tariff; None when it has no energy rates."""
    structure = item.get("energyratestructure")
    if not structure or not isinstance(structure, list):
        return None

    notes: list[str] = []
    first_period = structure[0]
    tiers: list[EnergyTier] = []
    for raw_tier in first_period:
        if not isinstance(raw_tier, dict):
            continue
        # URDB items carry explicit nulls ("adj": null) — `or 0.0` covers both
        # missing and null.
        rate = float(raw_tier.get("rate") or 0.0) + float(raw_tier.get("adj") or 0.0)
        max_usage = raw_tier.get("max")
        tiers.append(
            EnergyTier(
                rate_usd_per_kwh=rate,
                max_usage_kwh=float(max_usage) if max_usage is not None else None,
            )
        )
    if len(structure) > 1:
        notes.append(f"schedule has {len(structure)} rate periods; tiers shown are period 1 only")

    is_tou, is_seasonal = _schedule_shape(
        item.get("energyweekdayschedule"), item.get("energyweekendschedule")
    )
    if is_tou:
        notes.append("time-of-use structure: flat/tiered view is an approximation")
    elif is_seasonal:
        notes.append("seasonal rate periods: tiers shown are the first period")

    fixed = item.get("fixedchargefirstmeter")
    fixed_units = item.get("fixedchargeunits")
    fixed_monthly: float | None = None
    if fixed is not None:
        if fixed_units in (None, "$/month"):
            fixed_monthly = float(fixed)
        else:
            notes.append(f"fixed charge is {fixed} {fixed_units} (not converted)")

    return Tariff(
        utility=str(item.get("utility", "unknown")),
        name=str(item.get("name", "unnamed")),
        sector=str(item.get("sector", "")),
        energy_tiers=tiers,
        fixed_monthly_charge_usd=fixed_monthly,
        is_tou=is_tou,
        is_seasonal=is_seasonal,
        uri=str(item.get("uri", "")),
        source=item.get("source"),
        notes=notes,
    )


def _schedule_shape(*schedules: object) -> tuple[bool, bool]:
    """(is_tou, is_seasonal) from URDB 12x24 month-hour period matrices.

    TOU = the period changes within a single day; seasonal = constant within
    each day but different across months.
    """
    is_tou = False
    is_seasonal = False
    row_values: set[int] = set()
    for schedule in schedules:
        if not isinstance(schedule, list):
            continue
        for row in schedule:
            if not isinstance(row, list) or not row:
                continue
            distinct = {int(v) for v in row}
            if len(distinct) > 1:
                is_tou = True
            row_values.update(distinct)
    if not is_tou and len(row_values) > 1:
        is_seasonal = True
    return is_tou, is_seasonal


# ---------------------------------------------------------------- EIA


class EiaPricePoint(BaseModel):
    period: str  # "YYYY-MM"
    # EIA publishes null for small state/sector cells; tools filter these out.
    price_cents_per_kwh: float | None = Field(alias="price")
    state: str = Field(alias="stateid")
    sector: str = Field(alias="sectorid")


class EiaResponseBody(BaseModel):
    total: int
    data: list[EiaPricePoint]


class EiaResponse(BaseModel):
    response: EiaResponseBody
    warnings: list[dict[str, Any]] = Field(default_factory=list)
