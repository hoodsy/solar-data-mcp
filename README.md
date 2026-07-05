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

Install one server — `uvx solar-data-mcp` — and your agent gets all 18 tools, plus 11
skills that teach it how to use them, across four data domains: production modeling,
economics, market data, and forecasts. Every tool returns the same envelope — `data` +
`units` + `source` + `assumptions` + `warnings` — so the agent always knows what a
number means, where it came from, and which defaults were injected on its behalf.

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

## Example usage

> Compare annual production for an 8 kW system in Mesa, AZ at 10° vs 25° tilt.

The agent calls `compare_orientations`, gets both tilts modeled in one call, and answers
with production figures, the NREL source, and every assumption the model injected
(losses, azimuth, weather dataset). More to try:

- *"What's my payback period after incentives?"* → `estimate_roi`
- *"How long does permitting take in Phoenix, and who issues the permit?"* →
  `get_permitting_timelines` + `identify_ahj`
- *"What will my array generate tomorrow?"* → `forecast_generation`
- *"Brief me on the Texas solar market."* → `market_snapshot`

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

| Domain | Tool | What it does |
|---|---|---|
| Production | `estimate_production` | Annual and monthly AC production for a PV system (PVWatts v8) |
| | `get_solar_resource` | Annual/monthly solar irradiance (GHI, DNI) for a location (NSRDB) |
| | `compare_orientations` | Rank tilt × azimuth combinations by annual production |
| | `size_system_for_target` | Find the system size (kW) that produces a target annual kWh |
| Economics | `lookup_tariffs` | Retail electric rate schedules serving a point or utility (URDB) |
| | `get_electricity_prices` | State average retail electricity price with a monthly trend (EIA v2) |
| | `get_incentives` | Federal ITC (current law) + state/local programs (DSIRE) |
| | `sync_incentives` | Load a DSIRE program export into the local store |
| | `estimate_roi` | Screening ROI: payback, NPV, IRR, 25-yr cash flow |
| Market | `sync_tracking_the_sun` | Load an LBNL Tracking the Sun release into the local store |
| | `sync_solartrace` | Load a SolarTRACE export into the local store |
| | `query_installed_systems` | Aggregate stats from installed systems: median $/W, sizes, equipment |
| | `get_permitting_timelines` | Median permit, inspection, and interconnection days (SolarTRACE) |
| | `find_utility_scale_projects` | Ground-mounted utility-scale PV facilities (USPVDB) |
| | `identify_ahj` | Authority Having Jurisdiction + adopted codes for a point (SunSpec) |
| | `market_snapshot` | One-call state market overview: installs, $/W, permitting, big projects |
| Forecast | `forecast_generation` | Hourly generation forecast for the coming hours (Quartz open model) |
| | `compare_forecast_to_model` | Forecast vs typical-year baseline — "is today unusually sunny?" |

## Skills

Skills are markdown procedures, shipped inside the server, that teach an agent how to
orchestrate the tools end to end — correct ordering, sync prerequisites, which defaults
to override, and how to report results honestly. They're served as MCP resources:
`skill://solar/index` is the routing table, `skill://solar/<name>` the skill itself.
Skill-native hosts (like Claude Code) route on each skill's description automatically;
plain MCP hosts are pointed at the index by the server's instructions.

| Skill | Use it for |
|---|---|
| `solar-site-assessment` | "Should I go solar?" — sizing, production, incentives, ROI end to end |
| `solar-quote-review` | Check an installer's bid against market $/W, modeled production, payback |
| `solar-performance-check` | "Is my system doing what it should?" — forecasts and typical-year baselines |
| `solar-proposal-builder` | Installer proposal in one pass: design sweep, ROI at real cost, permitting |
| `solar-territory-expansion` | Compare candidate markets: rates, $/W, permitting friction, incentives |
| `solar-market-brief` | Standardized state brief: adoption, pricing, policy, infrastructure |
| `solar-pricing-analysis` | $/W trends and spreads over time and across states |
| `solar-utility-scale-scout` | Utility-scale landscape: biggest plants, battery share, pipeline |
| `solar-policy-incentive-scan` | Incentive landscape by state and install year |
| `solar-data-sync` | Load and refresh the bulk snapshots (Tracking the Sun, SolarTRACE, DSIRE) |
| `solar-data-conventions` | Envelope literacy: assumptions, warnings, provenance, error recovery |

Design rationale and the full catalog: [`docs/skills.md`](docs/skills.md).

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
