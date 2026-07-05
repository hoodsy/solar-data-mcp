# solar-data-mcp-forecast

MCP server wrapping the open [Quartz Solar Forecast](https://github.com/openclimatefix/quartz-solar-forecast)
model (Open Climate Fix): 48-hour generation forecasts plus "is today unusual?"
comparisons against PVWatts TMY expectations. No API key needed.
Part of [solar-data-mcp](https://github.com/hoodsy/solar-data-mcp).

## Installing the model

`quartz-solar-forecast` pins `pydantic==2.6.2`, which conflicts with the MCP SDK,
so it is not a declared dependency. Install it alongside (it runs fine on newer
pydantic; the pin is conservative):

```console
$ pip install solar-data-mcp-forecast
$ pip install --no-deps quartz-solar-forecast
$ pip install pv-site-prediction xarray xgboost openmeteo-requests requests-cache retry-requests
```

Without the model installed, the server still starts and its tools return an
error containing these instructions.

## Using forecasts with the combined `solar-data-mcp` server

An ephemeral `uvx` environment cannot hold the side-install above. Use a
persistent venv and point your agent at its entry point:

```console
$ python3 -m venv ~/.venvs/solar-data-mcp
$ ~/.venvs/solar-data-mcp/bin/pip install solar-data-mcp
$ ~/.venvs/solar-data-mcp/bin/pip install --no-deps quartz-solar-forecast
$ ~/.venvs/solar-data-mcp/bin/pip install pv-site-prediction xarray xgboost openmeteo-requests requests-cache retry-requests
```

Then in the agent config, replace `"command": "uvx", "args": ["solar-data-mcp"]`
with `"command": "~/.venvs/solar-data-mcp/bin/solar-data-mcp"`.
