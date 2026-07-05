<div align="center">

# ☀️ solar-mcp

**US solar data, agent-accessible.**

[![CI](https://github.com/hoodsy/solar-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/hoodsy/solar-mcp/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://github.com/hoodsy/solar-mcp/blob/main/pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-compatible-8A2BE2)](https://modelcontextprotocol.io)

Open-source [MCP](https://modelcontextprotocol.io) servers that bring US open solar data
to ChatGPT, Claude, and anything else that speaks MCP.

</div>

## What you can ask

> Compare annual production for an 8 kW system in Mesa, AZ at 10° vs 25° tilt.

With the `nrel-solar` server connected, your agent calls `compare_orientations` and
answers with production figures for both tilts. Every tool returns the same envelope —
`data` + `units` + `source` + `assumptions` + `warnings` — so the agent always knows what
a number means, where it came from, and which defaults were injected on its behalf.

| Server | Ask it | Data |
|---|---|---|
| `solar-mcp-nrel` | "What would an 8 kW system in Mesa produce?" | PVWatts v8 modeling, NSRDB irradiance |
| `solar-mcp-economics` | "What's my payback period after incentives?" | URDB tariffs, EIA prices, federal ITC + DSIRE |
| `solar-mcp-market` | "How long does permitting take in Phoenix?" | SolarTRACE, Tracking the Sun, USPVDB, AHJ lookup |
| `solar-mcp-forecast` | "What will my array generate tomorrow?" | Quartz open-source forecasts (OCF) |

## Quickstart

1. **Get a free NREL API key** — <https://developer.nlr.gov/signup/>
   (or use `DEMO_KEY` to try it out — 10 requests/hour).

2. **Add the server to your MCP client** — for Claude Desktop, merge this into
   `claude_desktop_config.json` (full example in
   [`examples/`](examples/claude_desktop_config.json)):

   ```json
   {
     "mcpServers": {
       "nrel-solar": {
         "command": "uvx",
         "args": ["--from", "solar-mcp-nrel", "nrel-solar-mcp"],
         "env": { "NREL_API_KEY": "YOUR_KEY_HERE" }
       }
     }
   }
   ```

3. **Restart your client and ask** — try the Mesa tilt comparison above.

Each server is one console script: `nrel-solar-mcp`, `solar-economics-mcp`,
`solar-market-mcp`, `solar-forecast-mcp`. Keys: NREL for production/irradiance,
OpenEI + EIA for economics (all free); USPVDB and the forecast model need none.
Verify keys and connectivity anytime:

```console
$ uvx --from solar-mcp-core solar-mcp doctor
```

## Development

```console
$ git clone https://github.com/hoodsy/solar-mcp && cd solar-mcp
$ uv sync                # install the workspace
$ uv run pytest          # fixture replay only, no network
```

Layout: `packages/core` (shared HTTP client, cache, envelope) plus one package per
server. Full spec: [`docs/SPEC.md`](docs/SPEC.md). Smallest possible client:
[`examples/example_client.py`](examples/example_client.py).

## License

MIT. Per-source data licensing/attribution is exposed as MCP resources
(`source://<name>/license`).
