"""Every recorded fixture, for every source, must be free of credentials."""

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = sorted((Path(__file__).parents[3] / "fixtures").glob("*/*.json"))

# Kept in sync with conftest.SECRET_FIELD_NAMES — any credential-bearing field a
# source might echo must be scrubbed, not just fields literally named api_key.
SECRET_FIELD_NAMES = frozenset(
    {"api_key", "token", "access_token", "authorization", "x-api-key", "apikey"}
)


def _secret_values(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if k.lower() in SECRET_FIELD_NAMES:
                found.append(str(v))
            else:
                found.extend(_secret_values(v))
    elif isinstance(value, list):
        for item in value:
            found.extend(_secret_values(item))
    return found


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_fixture_contains_no_credentials(path: Path) -> None:
    recorded = json.loads(path.read_text())
    assert "api_key" not in recorded["key"], "canonical key must exclude api_key"
    for value in _secret_values(recorded["response"]["json"]):
        assert value == "SCRUBBED", f"unscrubbed credential value in {path.name}"
    assert "DEMO_KEY" not in path.read_text(), "raw DEMO_KEY string in fixture body"
