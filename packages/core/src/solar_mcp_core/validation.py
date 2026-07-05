"""Shared input validation: coordinates and US geography.

One implementation, one error phrasing — every server rejects the same bad
input the same way, before any HTTP.
"""

from solar_mcp_core.errors import BadInput

STATE_CODES = frozenset(
    [
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "DC",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
    ]
)


def validate_state(state: str) -> str:
    upper = state.upper()
    if upper not in STATE_CODES:
        raise BadInput(field="state", value=state, allowed="two-letter US state code (e.g. CO)")
    return upper


def validate_lat_lon(lat: float, lon: float) -> None:
    if not -90 <= lat <= 90:
        raise BadInput(field="lat", value=lat, allowed="-90 to 90")
    if not -180 <= lon <= 180:
        raise BadInput(field="lon", value=lon, allowed="-180 to 180")


# PVWatts' documented system-size range; the forecast tools adopt it too so the
# suite rejects the same nonsense sizes everywhere.
CAPACITY_KW_MIN = 0.05
CAPACITY_KW_MAX = 500_000.0


def validate_capacity_kw(capacity_kw: float) -> None:
    if not CAPACITY_KW_MIN <= capacity_kw <= CAPACITY_KW_MAX:
        raise BadInput(
            field="capacity_kw",
            value=capacity_kw,
            allowed=f"{CAPACITY_KW_MIN} to {CAPACITY_KW_MAX:.0f} kW",
        )


def default_tilt_azimuth(
    lat: float, tilt_deg: float | None, azimuth_deg: float | None
) -> tuple[float, float, list[str], list[str]]:
    """Resolve the two orientation defaults every production-shaped tool shares.

    Returns (tilt, azimuth, assumptions, warnings): tilt defaults to |lat|,
    azimuth to 180 (south), and a southern-hemisphere site facing 180 gets the
    same advisory warning from every server.
    """
    assumptions: list[str] = []
    warnings: list[str] = []
    if tilt_deg is None:
        tilt_deg = min(abs(lat), 90.0)
        assumptions.append(
            f"tilt_deg not provided; defaulted to site latitude ({tilt_deg:.1f} deg)"
        )
    if azimuth_deg is None:
        azimuth_deg = 180.0
        assumptions.append("azimuth_deg not provided; defaulted to 180 (south-facing)")
    if lat < 0 and azimuth_deg == 180.0:
        warnings.append(
            "Southern-hemisphere site with south-facing azimuth: north-facing "
            "(azimuth_deg=0) is usually optimal below the equator."
        )
    return tilt_deg, azimuth_deg, assumptions, warnings
