# solar-mcp-core

Shared infrastructure for [solar-data-mcp](https://github.com/loganbernard/solar-data-mcp)
servers: HTTP client with retry/rate-limiting/caching, the `ToolResult` envelope, error
taxonomy, and the `solar-mcp doctor` CLI.

You usually don't install this directly — it comes in as a dependency of the server
packages (e.g. `solar-mcp-nrel`).
