# solar-data-mcp-core

Shared infrastructure for [solar-data-mcp](https://github.com/hoodsy/solar-data-mcp) —
US open solar data, agent-accessible over MCP. One install gives an agent production
modeling, solar economics, market intelligence, and generation forecasts, with every
number carrying `data + units + source + assumptions + warnings`.

This package is the plumbing the servers share: the HTTP client (retry, token-bucket
rate limiting, SQLite cache), the `ToolResult` envelope, the DuckDB bulk store, the
error taxonomy, and `solar-data-mcp doctor`. You usually don't install it directly.

Where to go instead:

| You want | Go to |
|---|---|
| Everything (18 tools + 11 skills + 4 report prompts, one install) | [`solar-data-mcp`](https://github.com/hoodsy/solar-data-mcp/blob/main/packages/solar-data-mcp/README.md) |
| Production & sizing only (PVWatts, NSRDB) | [`solar-data-mcp-nrel`](https://github.com/hoodsy/solar-data-mcp/blob/main/packages/nrel-solar/README.md) |
| Tariffs, incentives & ROI only | [`solar-data-mcp-economics`](https://github.com/hoodsy/solar-data-mcp/blob/main/packages/solar-economics/README.md) |
| Installed prices, permitting & utility-scale only | [`solar-data-mcp-market`](https://github.com/hoodsy/solar-data-mcp/blob/main/packages/solar-market/README.md) |
| 48-hour generation forecasts only | [`solar-data-mcp-forecast`](https://github.com/hoodsy/solar-data-mcp/blob/main/packages/solar-forecast/README.md) |
| The skill catalog, routing design & report templates | [`docs/skills.md`](https://github.com/hoodsy/solar-data-mcp/blob/main/docs/skills.md) |
| Quickstart & agent config snippets | [repo README](https://github.com/hoodsy/solar-data-mcp#quickstart) |
