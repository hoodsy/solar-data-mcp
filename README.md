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

Install one server — `uvx solar-data-mcp` — and your agent gets all 18 tools, 11
skills that teach it how to use them, and 4 ready-made report prompts, across four
data domains: production modeling, economics, market data, and forecasts. Every tool
returns the same envelope — `data` + `units` + `source` + `assumptions` + `warnings` —
so the agent always knows what a number means, where it came from, and which defaults
were injected on its behalf.

## What can you ask it?

- **Thinking about solar at home** — *"Would a 6 kW system pay off at my house?"* ·
  *"Is this $21,000 quote fair?"* · *"What will my array generate tomorrow?"*
- **Selling or installing solar** — *"Build a proposal for this customer"* ·
  *"How long does permitting take in Phoenix?"* · *"Where should we expand next?"*
- **Studying the market** — *"Brief me on the Texas solar market"* · *"How have
  installed prices trended in Colorado?"* · *"Which big plants have batteries?"*

Behind each question the agent picks the right tools (or a skill routes it), and every
number comes back with units, a source, and the assumptions made on your behalf.

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

3. **Restart your client and ask** — try
   *"Compare annual production for an 8 kW system in Mesa, AZ at 10° vs 25° tilt."*

Verify keys and connectivity anytime:

```console
$ uvx solar-data-mcp doctor
```

### Add it to your agent

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

### API keys

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

## Servers

`uvx solar-data-mcp` — the install above — serves all four domains on one stdio entry.
Each domain also ships as a standalone server:

| Domain | Data | Standalone server |
|---|---|---|
| Production | PVWatts v8 modeling, NSRDB irradiance | `uvx --from solar-data-mcp-nrel nrel-solar-mcp` |
| Economics | URDB tariffs, EIA prices, federal ITC + DSIRE | `uvx --from solar-data-mcp-economics solar-economics-mcp` |
| Market | SolarTRACE, Tracking the Sun, USPVDB, AHJ lookup | `uvx --from solar-data-mcp-market solar-market-mcp` |
| Forecast | Quartz open-source forecasts (OCF) | `uvx --from solar-data-mcp-forecast solar-forecast-mcp` |

Per-server config:
[`examples/claude_desktop_config.per-server.json`](examples/claude_desktop_config.per-server.json).

> ⚠️ Run the combined `solar-data` server **or** the per-domain servers, not both — and
> never `solar-economics` and `solar-market` side by side. Both open the same local
> DuckDB bulk store, which allows only one process at a time.

## Tools

Eighteen tools across four domains; parameter details live in each tool's docstring
and each domain package's README.

| Domain | Ask it about | Tools |
|---|---|---|
| [Production](packages/nrel-solar/README.md) | output, sunniness, sizing, roof orientation | `estimate_production`, `get_solar_resource`, `compare_orientations`, `size_system_for_target` |
| [Economics](packages/solar-economics/README.md) | tariffs, electricity prices, incentives, payback | `lookup_tariffs`, `get_electricity_prices`, `get_incentives`, `estimate_roi`, `sync_incentives` |
| [Market](packages/solar-market/README.md) | installed $/W, permitting times, utility-scale plants | `query_installed_systems`, `get_permitting_timelines`, `find_utility_scale_projects`, `identify_ahj`, `market_snapshot`, `sync_*` |
| [Forecast](packages/solar-forecast/README.md) | tomorrow's output, "is today unusual?" | `forecast_generation`, `compare_forecast_to_model` |

## Skills & reports

Skills are procedures shipped inside the combined server that teach an agent to chain
the tools correctly — ordering, sync prerequisites, honest reporting. They're MCP
resources: `skill://solar/index` routes by question shape, `skill://solar/<name>` is
the procedure. Grouped by who's asking:

- **Homeowners** — site assessment, quote review, performance check
- **Installers** — proposal builder, territory expansion
- **Analysts** — market brief, pricing analysis, utility-scale scout, incentive scan
- **Cross-cutting** — data sync (bulk snapshots), data conventions (envelope literacy)

Four of these render **reports** with a fixed document shape and are also exposed as
MCP prompts your host surfaces natively — `market_brief`, `site_assessment`,
`quote_review`, `proposal_builder` (in Claude Code: `/mcp__solar-data__market_brief`).

Full catalog, routing design, and report templates: [`docs/skills.md`](docs/skills.md).

## Development

```console
$ git clone https://github.com/hoodsy/solar-data-mcp && cd solar-data-mcp
$ uv sync                # install the workspace
$ uv run pytest          # fixture replay only, no network
```

Layout: `packages/core` (shared HTTP client, cache, envelope), one package per domain
server, and `packages/solar-data-mcp` (the umbrella that mounts all four on one stdio
entry). Smallest possible client:
[`examples/example_client.py`](examples/example_client.py).

## License

MIT. Per-source data licensing/attribution is exposed as MCP resources
(`source://<name>/license`).
