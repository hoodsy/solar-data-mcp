# solar-data-mcp-economics

MCP server answering "would solar pay off here?" with cited, decomposable numbers —
the economics domain of [solar-data-mcp](https://github.com/hoodsy/solar-data-mcp).

| Tool | Answers |
|---|---|
| `lookup_tariffs` | "Which rate schedules serve this address?" (OpenEI URDB) |
| `get_electricity_prices` | "What do people pay in Colorado, and which way is it trending?" (EIA v2) |
| `get_incentives` | "What can I claim this year?" (federal ITC + DSIRE snapshot) |
| `estimate_roi` | "Payback, NPV, IRR?" — the flagship composite, with a full audit trail |
| `sync_incentives` | Load a DSIRE program export into the local store |

Run standalone: `uvx --from solar-data-mcp-economics solar-economics-mcp`. Keys:
`OPENEI_API_KEY` (tariffs), `EIA_API_KEY` (prices), `NREL_API_KEY` (the production
model inside `estimate_roi`) — all free; a tool missing its key returns setup
instructions.

Most users want the combined
[`solar-data-mcp`](https://github.com/hoodsy/solar-data-mcp/blob/main/packages/solar-data-mcp/README.md)
server instead — all four domains plus the skill and report layer on one install.
Quickstart: [repo README](https://github.com/hoodsy/solar-data-mcp#quickstart).
