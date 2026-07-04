"""Contract tests: every recorded fixture must parse into our response models.

This is the upstream-drift alarm — when fixtures are re-recorded and NREL has
changed a response shape, these tests fail before any tool logic runs.
"""

import json
from pathlib import Path

import pytest
from solar_mcp_nrel.api import PVWATTS_PATH, SOLAR_RESOURCE_PATH
from solar_mcp_nrel.models import PVWattsResponse, SolarResourceResponse

FIXTURES = sorted((Path(__file__).parents[3] / "fixtures" / "nrel").glob("*.json"))


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_fixture_matches_response_model(path: Path) -> None:
    recorded = json.loads(path.read_text())
    key: str = recorded["key"]
    if recorded["response"]["status"] != 200:
        return  # error-path fixtures replay as-is; models only cover 200 bodies
    body = recorded["response"]["json"]

    if PVWATTS_PATH.removesuffix(".json") in key:
        parsed = PVWattsResponse.model_validate(body)
        assert len(parsed.outputs.ac_monthly) == 12
    elif SOLAR_RESOURCE_PATH.removesuffix(".json") in key:
        parsed_sr = SolarResourceResponse.model_validate(body)
        if not parsed_sr.errors:
            assert parsed_sr.outputs is not None
    else:
        pytest.fail(f"fixture {path.name} matches no known endpoint: {key}")


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_fixture_is_scrubbed(path: Path) -> None:
    recorded = json.loads(path.read_text())
    assert "api_key" not in recorded["key"]
    inputs = recorded["response"]["json"].get("inputs", {})
    if isinstance(inputs, dict) and "api_key" in inputs:
        assert inputs["api_key"] == "SCRUBBED"


def test_fixtures_exist() -> None:
    assert FIXTURES, "no fixtures recorded — run `uv run pytest --record`"
