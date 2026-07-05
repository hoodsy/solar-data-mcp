# solar-data-mcp

All US open solar data in **one MCP server**: NREL PVWatts production modeling,
tariffs & ROI economics, market intelligence, and generation forecasts — 18
tools, every result carrying data + units + source + assumptions + warnings.
Part of [solar-data-mcp](https://github.com/hoodsy/solar-data-mcp), which also ships
each domain as a standalone server.

## Add it to your agent

```json
{
  "mcpServers": {
    "solar-data": {
      "command": "uvx",
      "args": ["solar-data-mcp"],
      "env": {
        "NREL_API_KEY": "YOUR_KEY",
        "OPENEI_API_KEY": "YOUR_KEY",
        "EIA_API_KEY": "YOUR_KEY"
      }
    }
  }
}
```

Snippets for Claude Code, Codex, OpenCode, and Hermes live in the
[repo README](https://github.com/hoodsy/solar-data-mcp#add-it-to-your-agent).

## Keys (all free; every one optional to start)

| Env var | Unlocks | Get one |
| --- | --- | --- |
| `NREL_API_KEY` | estimate_production, get_solar_resource, compare_orientations, size_system_for_target, estimate_roi, compare_forecast_to_model | <https://developer.nlr.gov/signup/> (`DEMO_KEY` works for ~10 req/hr) |
| `OPENEI_API_KEY` | lookup_tariffs | <https://openei.org/services/api/signup/> |
| `EIA_API_KEY` | get_electricity_prices | <https://www.eia.gov/opendata/register.php> |
| `AHJ_REGISTRY_TOKEN` (optional) | identify_ahj | email <support@sunspec.org> |

Market tools (USPVDB, Tracking the Sun, SolarTRACE) and forecasts need no key.
The server starts with zero keys set — tools missing a key return setup
instructions instead of failing silently. Check your setup any time:

```console
$ uvx solar-data-mcp doctor
```

## Forecast model note

`forecast_generation` uses the open Quartz model, whose package pins an old
pydantic and cannot live in an ephemeral `uvx` environment. Forecast tools
degrade to an actionable install message without it; for real forecasts use a
persistent install (`uv tool install solar-data-mcp`) plus the steps in the
[solar-data-mcp-forecast README](https://github.com/hoodsy/solar-data-mcp/tree/main/packages/solar-forecast).
