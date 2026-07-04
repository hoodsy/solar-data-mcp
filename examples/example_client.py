"""Minimal MCP client for the nrel-solar server — no Claude required.

Launches the server as a stdio subprocess (exactly how Claude Desktop runs it),
lists its tools, reads a provenance resource, then runs the 60-second demo:
annual production for an 8 kW system in Mesa, AZ at 10 deg vs 25 deg tilt.

Run from the repo root:

    uv run python examples/example_client.py

Uses NREL_API_KEY from your environment (or .env via `uv run --env-file .env`);
falls back to NREL's public DEMO_KEY (10 requests/hour) so it works with zero
setup. Get a real key at https://developer.nlr.gov/signup/
"""

import asyncio
import os
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MESA_AZ = {"lat": 33.42, "lon": -111.83}

SERVER = StdioServerParameters(
    command=sys.executable,
    args=["-m", "solar_mcp_nrel.server"],
    env={**os.environ, "NREL_API_KEY": os.environ.get("NREL_API_KEY") or "DEMO_KEY"},
)


def show_envelope(name: str, envelope: dict[str, Any]) -> None:
    """Print a ToolResult the way an agent should read it: data, then caveats."""
    units = envelope["units"]
    print(f"\n=== {name} ===")
    for field, value in envelope["data"].items():
        unit = units.get(field, "")
        if isinstance(value, list) and len(value) > 4:
            value = f"[{value[0]:.0f} ... {value[-1]:.0f}] ({len(value)} values)"
        elif isinstance(value, float):
            value = f"{value:,.1f}"
        print(f"  {field:<22} {value} {unit}")
    source = envelope["source"]
    print(f"  source: {source['name']} (retrieved {source['retrieved_at']})")
    for line in envelope["assumptions"]:
        print(f"  assumed: {line}")
    for line in envelope["warnings"]:
        print(f"  warning: {line}")


async def call(session: ClientSession, tool: str, args: dict[str, Any]) -> None:
    result = await session.call_tool(tool, args)
    if result.isError:
        text = result.content[0].text if result.content else "unknown error"  # type: ignore[union-attr]
        print(f"\n=== {tool} ===\n  error: {text}")
        return
    assert result.structuredContent is not None
    show_envelope(tool, result.structuredContent)


async def main() -> None:
    async with (
        stdio_client(SERVER) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()

        tools = await session.list_tools()
        print("Tools exposed by nrel-solar:")
        for tool in tools.tools:
            summary = (tool.description or "").strip().splitlines()[0]
            print(f"  {tool.name:<24} {summary}")

        coverage = await session.read_resource("source://nrel/coverage")
        first_line = coverage.contents[0].text.splitlines()[0]  # type: ignore[union-attr]
        print(f"\nResource source://nrel/coverage: {first_line}")

        # The 60-second demo: how much does tilt matter in Mesa, AZ?
        await call(
            session,
            "compare_orientations",
            {**MESA_AZ, "system_capacity_kw": 8.0, "tilts": [10.0, 25.0], "azimuths": [180.0]},
        )
        await call(session, "get_solar_resource", MESA_AZ)


if __name__ == "__main__":
    asyncio.run(main())
