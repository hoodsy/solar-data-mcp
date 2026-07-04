"""Root pytest configuration for the solar-data-mcp workspace."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
