# solar-data-mcp

**US solar data, agent-accessible.**

Open-source [MCP](https://modelcontextprotocol.io) servers that make US open solar data
available to AI agents — Claude Desktop, Claude Code, or anything that speaks MCP. One
`pip install`, one free API key per source.

Every tool returns the same envelope — `data` + `units` + `source` + `assumptions` +
`warnings` — so an agent always knows what a number means, where it came from, and which
defaults were injected on its behalf. Nothing is ever silently defaulted.

| Server | Data | Status |
|---|---|---|
| `solar-mcp-nrel` | PVWatts v8 production modeling, NSRDB irradiance | **v0.1** |
| `solar-mcp-economics` | Tariffs (URDB), prices (EIA), incentives (DSIRE) | planned |
| `solar-mcp-market` | Permit timelines, installed systems, utility-scale plants | planned |
| `solar-mcp-forecast` | Quartz open-source generation forecasts | planned |

## Quickstart (≈5 minutes)

**1. Get a free NREL API key** (1 minute): <https://developer.nrel.gov/signup/>
   (or use `DEMO_KEY` to try it out — 30 requests/hour)

**2. Add the server to Claude Desktop** — merge this into your
`claude_desktop_config.json` (full example in [`examples/`](examples/claude_desktop_config.json)):

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

**3. Restart Claude Desktop and ask:**

> Compare annual production for an 8 kW system in Mesa, AZ at 10° vs 25° tilt.

Claude calls `compare_orientations` and answers with production figures, units, the NREL
source, and every assumption the model made (losses, azimuth, weather dataset).

### Verify your setup

```console
$ uvx --from solar-mcp-core solar-mcp doctor
cache dir: ~/.cache/solar-mcp (writable)
[nrel] key present (NREL_API_KEY)
[nrel] PASS — live ping OK, 998 requests remaining this hour
```

## Tools (nrel-solar)

| Tool | Question it answers |
|---|---|
| `estimate_production` | "What would an 8 kW system in Mesa produce?" |
| `get_solar_resource` | "How sunny is it in Denver, really?" |
| `compare_orientations` | "How bad is my north-facing roof?" |
| `size_system_for_target` | "My home uses 9,000 kWh/yr — what size system covers it?" |

The server also exposes MCP resources `source://nrel/license` and
`source://nrel/coverage` so agents can cite provenance and coverage limits.

## Design

- **Envelope everywhere** — one result contract across all servers; injected defaults are
  spelled out in `assumptions`, upstream caveats surface in `warnings`
- **Cache-first** — 30-day SQLite HTTP cache (TMY results are deterministic per
  location); NREL's 1,000 req/hr rolling limit is respected by a token bucket, 429s are
  never retried, and stale cache serves as a quota fallback
- **Validated before HTTP** — inputs are checked against NREL's documented ranges first;
  errors name the exact field and allowed range so agents self-correct
- **Zero live calls in CI** — tests replay recorded fixtures; `pytest --record`
  refreshes them locally with a real key

## Development

```console
$ git clone https://github.com/loganbernard/solar-data-mcp && cd solar-data-mcp
$ uv sync                  # install the workspace
$ uv run pytest            # fixture replay only, no network
$ uv run ruff check . && uv run mypy
$ uv run pytest --record   # refresh fixtures (needs NREL_API_KEY in .env)
```

Repo layout: `packages/core` (shared HTTP client, cache, envelope, `solar-mcp` CLI) and
`packages/nrel-solar` (the Phase 1 server). Full spec in [`docs/SPEC.md`](docs/SPEC.md).

## License

MIT. Data licensing/attribution notes per source are exposed as MCP resources
(`source://<name>/license`).
