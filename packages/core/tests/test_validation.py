import pytest
from solar_mcp_core.errors import BadInput
from solar_mcp_core.validation import STATE_CODES, validate_lat_lon, validate_state


def test_state_codes_cover_fifty_states_plus_dc() -> None:
    assert len(STATE_CODES) == 51


def test_validate_state_normalizes_case() -> None:
    assert validate_state("co") == "CO"
    with pytest.raises(BadInput, match="state"):
        validate_state("XX")


def test_validate_lat_lon_bounds() -> None:
    validate_lat_lon(90.0, -180.0)  # inclusive bounds
    with pytest.raises(BadInput) as excinfo:
        validate_lat_lon(90.1, 0.0)
    assert excinfo.value.field == "lat"
    with pytest.raises(BadInput) as excinfo:
        validate_lat_lon(0.0, -180.1)
    assert excinfo.value.field == "lon"
