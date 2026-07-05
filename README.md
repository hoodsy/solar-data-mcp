<div align="center">

# ☀️ solar-data-mcp

**US solar data, agent-accessible.**

[![CI](https://github.com/hoodsy/solar-data-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/hoodsy/solar-data-mcp/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://github.com/hoodsy/solar-data-mcp/blob/main/pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-compatible-8A2BE2)](https://modelcontextprotocol.io)

One [MCP](https://modelcontextprotocol.io) server that brings US open solar data
to Claude, ChatGPT, and anything else that speaks MCP.

</div>

## What you can ask

> Compare annual production for an 8 kW system in Mesa, AZ at 10° vs 25° tilt.

Install one server — `uvx solar-data-mcp` — and your agent gets all 18 tools across four
data domains. Every tool returns the same envelope — `data` + `units` + `source` +
`assumptions` + `warnings` — so the agent always knows what a number means, where it came
from, and which defaults were injected on its behalf.

| Domain | Ask it | Data |
|---|---|---|
| Production | "What would an 8 kW system in Mesa produce?" | PVWatts v8 modeling, NSRDB irradiance |
| Economics | "What's my payback period after incentives?" | URDB tariffs, EIA prices, federal ITC + DSIRE |
| Market | "How long does permitting take in Phoenix?" | SolarTRACE, Tracking the Sun, USPVDB, AHJ lookup |
| Forecast | "What will my array generate tomorrow?" | Quartz open-source forecasts (OCF) |

## Quickstart

1. **Get a free NREL API key** — <https://developer.nlr.gov/signup/>
   (or use `DEMO_KEY` to try it out — 10 requests/hour).

2. **Add the server to your agent** — snippets for every major agent below; for
   Claude Desktop, merge this into `claude_desktop_config.json`
   (full example in [`examples/`](examples/claude_desktop_config.json)):

   ```json
   {
     "mcpServers": {
       "solar-data": {
         "command": "uvx",
         "args": ["solar-data-mcp"],
         "env": {
           "NREL_API_KEY": "YOUR_KEY_HERE",
           "OPENEI_API_KEY": "YOUR_KEY_HERE",
           "EIA_API_KEY": "YOUR_KEY_HERE"
         }
       }
     }
   }
   ```

   Only `NREL_API_KEY` is needed to start: the server runs with any subset of keys,
   and a tool missing its key returns setup instructions instead of failing silently.

3. **Restart your client and ask** — try the Mesa tilt comparison above.

Verify keys and connectivity anytime:

```console
$ uvx solar-data-mcp doctor
```

## Add it to your agent

**Claude Code**

```console
$ claude mcp add solar-data \
    --env NREL_API_KEY=YOUR_KEY --env OPENEI_API_KEY=YOUR_KEY --env EIA_API_KEY=YOUR_KEY \
    -- uvx solar-data-mcp
```

(or commit the quickstart JSON to your project's `.mcp.json`)

**Codex CLI** — `~/.codex/config.toml`:

```toml
[mcp_servers.solar-data]
command = "uvx"
args = ["solar-data-mcp"]

[mcp_servers.solar-data.env]
NREL_API_KEY = "YOUR_KEY_HERE"
OPENEI_API_KEY = "YOUR_KEY_HERE"
EIA_API_KEY = "YOUR_KEY_HERE"
```

(or `codex mcp add solar-data --env NREL_API_KEY=YOUR_KEY -- uvx solar-data-mcp`;
use `env_vars = ["NREL_API_KEY"]` to forward keys from your shell instead of
hardcoding them)

**OpenCode** — `opencode.json` in your project (or `~/.config/opencode/opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "solar-data": {
      "type": "local",
      "command": ["uvx", "solar-data-mcp"],
      "enabled": true,
      "environment": {
        "NREL_API_KEY": "YOUR_KEY_HERE",
        "OPENEI_API_KEY": "YOUR_KEY_HERE",
        "EIA_API_KEY": "YOUR_KEY_HERE"
      }
    }
  }
}
```

**Hermes** — `~/.hermes/config.yaml`, then `/reload-mcp`:

```yaml
mcp_servers:
  solar-data:
    command: "uvx"
    args: ["solar-data-mcp"]
    env:
      NREL_API_KEY: "YOUR_KEY_HERE"
      OPENEI_API_KEY: "YOUR_KEY_HERE"
      EIA_API_KEY: "YOUR_KEY_HERE"
```

**Claude Desktop** — the quickstart JSON above.

**Anything else that speaks MCP (stdio)** — command `uvx`, args `["solar-data-mcp"]`,
keys in the `env` block.

## Keys

All free, and every one optional — the server starts with none set.

| Env var | Unlocks | Get one |
|---|---|---|
| `NREL_API_KEY` | estimate_production, get_solar_resource, compare_orientations, size_system_for_target, estimate_roi, compare_forecast_to_model | <https://developer.nlr.gov/signup/> |
| `OPENEI_API_KEY` | lookup_tariffs | <https://openei.org/services/api/signup/> |
| `EIA_API_KEY` | get_electricity_prices | <https://www.eia.gov/opendata/register.php> |
| `AHJ_REGISTRY_TOKEN` (optional) | identify_ahj | email <support@sunspec.org> |

Market tools (USPVDB, Tracking the Sun, SolarTRACE) and forecasts need no key.
Full forecast output additionally needs the Quartz model installed into a persistent
environment (see [`packages/solar-forecast/`](packages/solar-forecast/README.md));
without it the forecast tools return install instructions.

## Advanced: one server per domain

Each domain also ships standalone — `nrel-solar-mcp` (solar-data-mcp-nrel),
`solar-economics-mcp` (solar-data-mcp-economics), `solar-market-mcp`
(solar-data-mcp-market), `solar-forecast-mcp` (solar-data-mcp-forecast) — launched as
`uvx --from solar-data-mcp-nrel nrel-solar-mcp`, etc. Per-server config:
[`examples/claude_desktop_config.per-server.json`](examples/claude_desktop_config.per-server.json).

> ⚠️ Run the combined `solar-data` server **or** the per-domain servers, not both — and
> never `solar-economics` and `solar-market` side by side. Both open the same local
> DuckDB bulk store, which allows only one process at a time.

## Development

```console
$ git clone https://github.com/hoodsy/solar-data-mcp && cd solar-data-mcp
$ uv sync                # install the workspace
$ uv run pytest          # fixture replay only, no network
```

Layout: `packages/core` (shared HTTP client, cache, envelope), one package per domain
server, and `packages/solar-data-mcp` (the umbrella that mounts all four on one stdio
entry). Full spec: [`docs/SPEC.md`](docs/SPEC.md). Smallest possible client:
[`examples/example_client.py`](examples/example_client.py).

## License

MIT. Per-source data licensing/attribution is exposed as MCP resources
(`source://<name>/license`).
