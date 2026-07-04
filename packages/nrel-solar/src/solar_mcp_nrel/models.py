"""Request/response models for the NREL PVWatts v8 and Solar Resource v1 APIs.

Request constraints mirror the documented PVWatts v8 ranges exactly, so every
bad input is rejected here — before any HTTP call — with the field name and
allowed range in the error.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator
from solar_mcp_core.errors import BadInput


@dataclass(frozen=True)
class SystemSpec:
    """Site + system parameters shared by every PVWatts-backed tool.

    None means "not specified by the caller": the documented default is
    injected at request-build time and recorded in the envelope's
    assumptions — so assumptions list exactly the values we chose, never
    values the caller passed explicitly.
    """

    lat: float
    lon: float
    tilt_deg: float | None = None
    azimuth_deg: float | None = None
    array_type: str | None = None
    module_type: str | None = None
    losses_pct: float | None = None
    dc_ac_ratio: float | None = None


class ArrayType(StrEnum):
    FIXED_OPEN = "fixed_open"
    FIXED_ROOF = "fixed_roof"
    ONE_AXIS = "1axis"
    ONE_AXIS_BACKTRACK = "1axis_backtrack"
    TWO_AXIS = "2axis"

    @property
    def code(self) -> int:
        return {
            ArrayType.FIXED_OPEN: 0,
            ArrayType.FIXED_ROOF: 1,
            ArrayType.ONE_AXIS: 2,
            ArrayType.ONE_AXIS_BACKTRACK: 3,
            ArrayType.TWO_AXIS: 4,
        }[self]


class ModuleType(StrEnum):
    STANDARD = "standard"
    PREMIUM = "premium"
    THIN_FILM = "thin_film"

    @property
    def code(self) -> int:
        return {
            ModuleType.STANDARD: 0,
            ModuleType.PREMIUM: 1,
            ModuleType.THIN_FILM: 2,
        }[self]


class PVWattsRequest(BaseModel):
    """Validated PVWatts v8 request. Ranges are NREL's documented limits."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    system_capacity: float = Field(ge=0.05, le=500000, description="kW DC")
    tilt: float = Field(ge=0, le=90, description="degrees from horizontal")
    azimuth: float = Field(ge=0, lt=360, description="degrees; 180 = south. 360 is invalid")
    array_type: ArrayType
    module_type: ModuleType
    losses: float = Field(ge=-5, le=99, description="percent system losses")
    # gt alone would admit +inf, which survives to URL building and breaks there
    dc_ac_ratio: float = Field(gt=0, allow_inf_nan=False)
    bifaciality: float | None = Field(default=None, ge=0, le=1)
    albedo: float | None = Field(default=None, gt=0, lt=1)

    def to_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "lat": self.lat,
            "lon": self.lon,
            "system_capacity": self.system_capacity,
            "tilt": self.tilt,
            "azimuth": self.azimuth,
            "array_type": self.array_type.code,
            "module_type": self.module_type.code,
            "losses": self.losses,
            "dc_ac_ratio": self.dc_ac_ratio,
            "dataset": "nsrdb",
            "timeframe": "monthly",
        }
        if self.bifaciality is not None:
            params["bifaciality"] = self.bifaciality
        if self.albedo is not None:
            params["albedo"] = self.albedo
        return params


class StationInfo(BaseModel):
    lat: float
    lon: float
    elev: float | None = None
    tz: float | None = None
    location: str | None = None
    city: str | None = None
    state: str | None = None
    solar_resource_file: str | None = None
    distance: int | None = None  # meters; absent when radius=0
    weather_data_source: str | None = None


class PVWattsOutputs(BaseModel):
    ac_annual: float  # kWh AC
    ac_monthly: list[float]  # 12 values, kWh AC
    dc_monthly: list[float] | None = None
    poa_monthly: list[float] | None = None
    solrad_monthly: list[float] | None = None
    solrad_annual: float  # kWh/m2/day
    capacity_factor: float  # PERCENT (e.g. 11.79), not a fraction


class PVWattsResponse(BaseModel):
    outputs: PVWattsOutputs
    station_info: StationInfo | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    version: str | None = None


class MonthlySeries(BaseModel):
    annual: float
    monthly: dict[str, float]


class SolarResourceOutputs(BaseModel):
    avg_dni: MonthlySeries | None = None
    avg_ghi: MonthlySeries | None = None
    avg_lat_tilt: MonthlySeries | None = None

    @field_validator("avg_dni", "avg_ghi", "avg_lat_tilt", mode="before")
    @classmethod
    def no_data_string_is_none(cls, value: object) -> object:
        # Out-of-coverage responses carry the literal string "no data" (HTTP 200,
        # empty errors) instead of null — observed live 2026-07-05.
        return None if isinstance(value, str) else value


class SolarResourceResponse(BaseModel):
    outputs: SolarResourceOutputs | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    version: str | None = None


_RANGE_HINTS: dict[str, str] = {
    "lat": "-90 to 90",
    "lon": "-180 to 180",
    "system_capacity": "0.05 to 500000 kW",
    "tilt": "0 to 90 degrees",
    "azimuth": "0 to <360 degrees (360 itself is invalid; use 0)",
    "losses": "-5 to 99 percent",
    "dc_ac_ratio": "> 0",
    "bifaciality": "0 to 1",
    "albedo": "> 0 and < 1 (exclusive)",
    "array_type": "one of: fixed_open, fixed_roof, 1axis, 1axis_backtrack, 2axis",
    "module_type": "one of: standard, premium, thin_film",
}


def build_pvwatts_request(**kwargs: Any) -> PVWattsRequest:
    """Validate raw inputs into a PVWattsRequest, raising BadInput on failure."""
    try:
        return PVWattsRequest(**kwargs)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = str(first["loc"][0]) if first["loc"] else "input"
        allowed = _RANGE_HINTS.get(field, first["msg"])
        raise BadInput(field=field, value=first.get("input"), allowed=allowed) from exc


def validate_coords(lat: float, lon: float) -> None:
    """Range-check bare coordinates for endpoints without a request model."""
    if not -90 <= lat <= 90:
        raise BadInput(field="lat", value=lat, allowed=_RANGE_HINTS["lat"])
    if not -180 <= lon <= 180:
        raise BadInput(field="lon", value=lon, allowed=_RANGE_HINTS["lon"])
