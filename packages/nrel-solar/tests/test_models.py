from typing import Any

import pytest
from solar_mcp_core.errors import BadInput
from solar_mcp_nrel.models import (
    ArrayType,
    ModuleType,
    build_pvwatts_request,
)

BASE: dict[str, Any] = {
    "lat": 40.0,
    "lon": -105.0,
    "system_capacity": 4.0,
    "tilt": 20.0,
    "azimuth": 180.0,
    "array_type": ArrayType.FIXED_ROOF,
    "module_type": ModuleType.STANDARD,
    "losses": 14.0,
    "dc_ac_ratio": 1.2,
}


def build(**overrides: Any) -> None:
    build_pvwatts_request(**{**BASE, **overrides})


# (field, invalid values, valid boundary values) per documented PVWatts v8 ranges
RANGES = [
    ("lat", [-90.1, 90.1], [-90.0, 90.0]),
    ("lon", [-180.1, 180.1], [-180.0, 180.0]),
    ("system_capacity", [0.049, 500000.1], [0.05, 500000.0]),
    ("tilt", [-0.1, 90.1], [0.0, 90.0]),
    ("azimuth", [-0.1, 360.0], [0.0, 359.9]),
    ("losses", [-5.1, 99.1], [-5.0, 99.0]),
    ("dc_ac_ratio", [0.0, -1.0, float("inf"), float("nan")], [0.01, 2.0]),
    ("bifaciality", [-0.1, 1.1], [0.0, 1.0]),
    ("albedo", [0.0, 1.0], [0.001, 0.999]),
]


@pytest.mark.parametrize(("field", "invalid", "valid"), RANGES)
def test_range_boundaries(field: str, invalid: list[float], valid: list[float]) -> None:
    for value in invalid:
        with pytest.raises(BadInput) as excinfo:
            build(**{field: value})
        assert excinfo.value.field == field, f"{field}={value} blamed on wrong field"
        assert field in str(excinfo.value)
    for value in valid:
        build(**{field: value})  # must not raise


def test_bad_input_message_names_allowed_range() -> None:
    with pytest.raises(BadInput, match="0 to 90"):
        build(tilt=95)
    with pytest.raises(BadInput, match="360 itself is invalid"):
        build(azimuth=360)


def test_array_type_codes() -> None:
    assert [t.code for t in ArrayType] == [0, 1, 2, 3, 4]
    assert ArrayType("1axis") is ArrayType.ONE_AXIS
    assert ArrayType("fixed_roof").code == 1


def test_module_type_codes() -> None:
    assert [t.code for t in ModuleType] == [0, 1, 2]
    assert ModuleType("thin_film").code == 2


def test_to_params_encodes_enums_and_defaults() -> None:
    request = build_pvwatts_request(**BASE)
    params = request.to_params()
    assert params["array_type"] == 1  # fixed_roof
    assert params["module_type"] == 0  # standard
    assert params["dataset"] == "nsrdb"
    assert params["timeframe"] == "monthly"
    assert "albedo" not in params
    assert "bifaciality" not in params


def test_to_params_includes_optionals_when_set() -> None:
    request = build_pvwatts_request(**{**BASE, "albedo": 0.3, "bifaciality": 0.7})
    params = request.to_params()
    assert params["albedo"] == 0.3
    assert params["bifaciality"] == 0.7


def test_solar_resource_no_data_strings_normalize_to_none() -> None:
    from solar_mcp_nrel.models import SolarResourceResponse

    # Live out-of-coverage shape observed 2026-07-05: HTTP 200, empty errors,
    # and the literal string "no data" in place of each series.
    response = SolarResourceResponse.model_validate(
        {
            "version": "1.1.0",
            "errors": [],
            "warnings": [],
            "outputs": {"avg_dni": "no data", "avg_ghi": "no data", "avg_lat_tilt": "no data"},
        }
    )
    assert response.outputs is not None
    assert response.outputs.avg_ghi is None
    assert response.outputs.avg_dni is None
