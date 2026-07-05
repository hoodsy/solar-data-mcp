# solar-data-mcp-market

MCP server for US solar market intelligence — the market domain of
[solar-data-mcp](https://github.com/hoodsy/solar-data-mcp).

| Tool | Answers |
|---|---|
| `query_installed_systems` | "Median $/W in CO since 2022?" (LBNL Tracking the Sun) |
| `get_permitting_timelines` | "How long does permitting take in Denver?" (SolarTRACE) |
| `find_utility_scale_projects` | "Biggest solar farms in Texas — batteries?" (USPVDB, live) |
| `identify_ahj` | "Who issues the permit here?" (SunSpec registry; token by email) |
| `market_snapshot` | One-call state overview: installs, $/W, permitting, big projects |
| `sync_tracking_the_sun` / `sync_solartrace` | Load the bulk datasets into the local store |

The bulk datasets sync into a local DuckDB store with explicit `sync_*` tools and
cited vintages — query tools tell you which sync they need. No API keys required.

Run standalone: `uvx --from solar-data-mcp-market solar-market-mcp` — but not
alongside `solar-economics-mcp` (both open the same single-process DuckDB store).

Most users want the combined
[`solar-data-mcp`](https://github.com/hoodsy/solar-data-mcp/blob/main/packages/solar-data-mcp/README.md)
server instead — all four domains plus the skill and report layer on one install.
Quickstart: [repo README](https://github.com/hoodsy/solar-data-mcp#quickstart).
