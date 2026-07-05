# solar-data-mcp-nrel

MCP server for NREL solar APIs — the production-modeling domain of
[solar-data-mcp](https://github.com/hoodsy/solar-data-mcp).

| Tool | Answers |
|---|---|
| `estimate_production` | "What would an 8 kW system in Mesa produce?" (PVWatts v8) |
| `get_solar_resource` | "How sunny is Denver, really?" (NSRDB GHI/DNI) |
| `compare_orientations` | "How bad is my north-facing roof?" (tilt × azimuth sweep) |
| `size_system_for_target` | "My home uses 9,000 kWh/yr — what size covers it?" |

Run standalone: `uvx --from solar-data-mcp-nrel nrel-solar-mcp` with a free
`NREL_API_KEY` (<https://developer.nlr.gov/signup/>; `DEMO_KEY` works at ~10 req/hr).

Most users want the combined
[`solar-data-mcp`](https://github.com/hoodsy/solar-data-mcp/blob/main/packages/solar-data-mcp/README.md)
server instead — all four domains plus the skill and report layer on one install.
Quickstart: [repo README](https://github.com/hoodsy/solar-data-mcp#quickstart).
