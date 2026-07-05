# solar-data-mcp

**US solar data, agent-accessible.**

Open-source [MCP](https://modelcontextprotocol.io) servers that make US open solar data
available to AI agents — Claude Desktop, Claude Code, or anything that speaks MCP. One
`pip install`, one free API key per source.

Every tool returns the same envelope — `data` + `units` + `source` + `assumptions` +
`warnings` — so an agent always knows what a number means, where it came from, and which
defaults were injected on its behalf. Nothing is ever silently defaulted.

| Server | Data | Tools |
|---|---|---|
| `solar-mcp-nrel` | PVWatts v8 production modeling, NSRDB irradiance | estimate_production, get_solar_resource, compare_orientations, size_system_for_target |
| `solar-mcp-economics` | Tariffs (URDB), prices (EIA v2), incentives (federal ITC + DSIRE) | lookup_tariffs, get_electricity_prices, get_incentives, sync_incentives, **estimate_roi** |
| `solar-mcp-market` | Permitting timelines (SolarTRACE), installed systems (Tracking the Sun), utility-scale plants (USPVDB), AHJ lookup | sync_* loaders, query_installed_systems, get_permitting_timelines, find_utility_scale_projects, identify_ahj, market_snapshot |
| `solar-mcp-forecast` | Quartz open-source generation forecasts (OCF) | forecast_generation, compare_forecast_to_model |

Console scripts: `nrel-solar-mcp`, `solar-economics-mcp`, `solar-market-mcp`,
`solar-forecast-mcp` — each is one line of Claude Desktop config. API keys:
NREL for production/irradiance, OpenEI + EIA for economics (all free); USPVDB
and the forecast model need none.

## Quickstart (≈5 minutes)

**1. Get a free NREL API key** (1 minute): <https://developer.nlr.gov/signup/>
   (or use `DEMO_KEY` to try it out — 10 requests/hour)

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

### No Claude? Try it from the terminal

[`examples/example_client.py`](examples/example_client.py) is a ~90-line MCP client that
launches the server the same way Claude Desktop does, lists its tools, and runs the Mesa
AZ tilt comparison:

```console
$ git clone https://github.com/hoodsy/solar-mcp && cd solar-data-mcp
$ uv sync
$ NREL_API_KEY=DEMO_KEY uv run python examples/example_client.py
Tools exposed by nrel-solar:
  estimate_production      Estimate annual and monthly AC production for a PV system...
  ...
=== compare_orientations ===
  best                   {'tilt': 25.0, 'azimuth': 180.0}
  ...
```

It's also the smallest starting point for wiring these tools into your own agent.

### Verify your setup

```console
$ uvx --from solar-mcp-core solar-mcp doctor
cache dir: ~/.cache/solar-mcp (writable)
[nrel] key present (NREL_API_KEY)
[nrel] PASS — live ping OK, 998 requests remaining this hour
[openei] key present (OPENEI_API_KEY)
[openei] PASS — live ping OK
[eia] FAIL — EIA_API_KEY not set. Setup: https://www.eia.gov/opendata/register.php
[dsire] no key required
[dsire] SKIP — no liveness ping defined for this source
[uspvdb] no key required
[uspvdb] PASS — live ping OK
[ahj] SKIP — optional source; set AHJ_REGISTRY_TOKEN to enable
...
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
$ git clone https://github.com/hoodsy/solar-mcp && cd solar-data-mcp
$ uv sync                  # install the workspace
$ uv run pytest            # fixture replay only, no network
$ uv run ruff check . && uv run mypy
$ uv run pytest --record   # refresh fixtures (needs NREL_API_KEY in .env)
```

Repo layout: `packages/core` (shared HTTP client, caches, envelope, `solar-mcp` CLI)
plus one package per server: `nrel-solar`, `solar-economics`, `solar-market`,
`solar-forecast`. Full spec in [`docs/SPEC.md`](docs/SPEC.md).

## License

MIT. Data licensing/attribution notes per source are exposed as MCP resources
(`source://<name>/license`).
