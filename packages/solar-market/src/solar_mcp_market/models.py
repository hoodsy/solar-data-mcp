"""Models and input validation for the market sources."""

from pydantic import BaseModel, Field
from solar_mcp_core.errors import BadInput


class Bbox(BaseModel):
    """west/south/east/north in degrees."""

    west: float
    south: float
    east: float
    north: float


def validate_bbox(bbox: list[float]) -> Bbox:
    if len(bbox) != 4:
        raise BadInput(field="bbox", value=bbox, allowed="[west, south, east, north] (4 numbers)")
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180) or not (-90 <= south < north <= 90):
        raise BadInput(
            field="bbox",
            value=bbox,
            allowed="west < east within -180..180 and south < north within -90..90",
        )
    return Bbox(west=west, south=south, east=east, north=north)


class AhjRecord(BaseModel):
    """One AHJ Registry result, loosely validated (upstream is token-gated and
    the request shape is unverified offline — see identify_ahj)."""

    name: str | None = Field(default=None, validation_alias="AHJName")
    level: str | None = Field(default=None, validation_alias="AHJLevelCode")
    building_code: str | None = Field(default=None, validation_alias="BuildingCode")
    electric_code: str | None = Field(default=None, validation_alias="ElectricCode")
    fire_code: str | None = Field(default=None, validation_alias="FireCode")
    residential_code: str | None = Field(default=None, validation_alias="ResidentialCode")


class UspvdbProject(BaseModel):
    """One USPVDB facility record (subset of the EIA-860-derived attributes)."""

    case_id: int
    p_name: str
    p_state: str
    p_county: str | None = None
    p_year: int | None = None
    p_cap_ac: float | None = None  # MW-AC
    p_cap_dc: float | None = None  # MW-DC
    ylat: float | None = None
    xlong: float | None = None
    p_axis: str | None = None
    p_battery: str | None = None
    eia_id: int | None = None
