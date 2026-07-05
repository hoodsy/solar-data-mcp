# solar-data-mcp — Build Spec

> Exported from the Notion build spec ("solar-data-mcp — Build Spec", 2026-07-05).
> Notion remains the editing home; this file is the in-repo snapshot the build follows.
> Detailed Phase 2–4 specs live in Notion sub-pages and are exported when each phase starts.

## Vision

An open-source monorepo of MCP (Model Context Protocol) servers that makes US open solar
data accessible to AI agents. One `pip install`, one free API key per source, and any MCP
client (Claude Desktop, Claude Code, custom agents) can estimate production, query tariffs
and incentives, analyze permitting timelines, and pull market data.

**Tagline:** *US solar data, agent-accessible.*

## Goals

1. Ship `nrel-solar` (Phase 1) as a standalone useful v0.1 within ~3 weeks
2. Every tool returns typed, cited, unit-annotated results an agent can reason about
3. 100% open: free API keys or public bulk data only in core servers; MIT license
4. Zero API calls in CI — recorded fixtures make tests deterministic
5. Composite tools (e.g. `estimate_roi`) that chain sources into answers no single API provides

## Non-goals

- Not a web app or dashboard (agents are the UI)
- Not a data warehouse — bulk sources are cached locally per-user, not re-hosted
- No proprietary data in core: Google Solar API ships only as an optional adapter
- Not international (v1 is US-only; Quartz forecast module is the exception)

## Phase summary

| Phase | Server | Sources | Status |
|---|---|---|---|
| 1 | `nrel-solar` | PVWatts v8, NSRDB | **Shipped** |
| 2 | `solar-economics` | OpenEI URDB, EIA v2, DSIRE | **Shipped** |
| 3 | `solar-market` | SolarTRACE, Tracking the Sun, USPVDB, AHJ Registry | **Shipped** |
| 4 | `solar-forecast` + adapters | Quartz (OCF), Google Solar (optional) | **Shipped** (Quartz; Google adapter excluded) |

---

# Architecture & shared infrastructure

## Monorepo layout

```
solar-data-mcp/
├── packages/
│   ├── core/                  # shared: http client, cache, schemas, units
│   │   └── src/solar_mcp_core/
│   ├── nrel-solar/            # Phase 1
│   ├── solar-economics/       # Phase 2
│   ├── solar-market/          # Phase 3
│   └── solar-forecast/        # Phase 4
├── fixtures/                  # recorded API responses for tests
├── examples/                  # agent demos, Claude Desktop configs
├── docs/
└── pyproject.toml             # uv workspace
```

- **Tooling:** Python 3.11+, `uv` workspaces, `ruff`, `mypy --strict`, `pytest`
- **MCP framework:** official Python MCP SDK (`FastMCP`) — stdio transport primary
- Each package is independently pip-installable (`solar-mcp-nrel`, etc.) and exposes a
  console script (`nrel-solar-mcp`) so Claude Desktop config is one line

## solar_mcp_core (shared library)

### HTTP client
- `httpx.AsyncClient` wrapper with: retry w/ exponential backoff (respect `Retry-After`),
  per-source rate limiter (token bucket), request/response logging behind `SOLAR_MCP_DEBUG=1`
- NREL developer API allows 1,000 req/hr per key — limiter defaults per source in a
  `SourceConfig` registry

### Cache
Two tiers:
1. **HTTP cache** — SQLite (`~/.cache/solar-mcp/http.db`), keyed on canonicalized
   URL+params, TTL per source (PVWatts: 30d — TMY results are static for a lat/lon;
   tariffs: 7d; forecasts: none)
2. **Bulk data store** — DuckDB (`~/.cache/solar-mcp/bulk.duckdb`) for Phase 3 datasets,
   populated by explicit `sync_*` tools

Rationale: caching is a correctness feature (rate limits) and a UX feature (agents retry a lot).

### Result envelope

Every tool returns the same envelope so agents learn one contract:

```python
class ToolResult(BaseModel):
    data: dict            # tool-specific typed payload
    units: dict[str, str] # field -> unit, e.g. {"ac_annual": "kWh/yr"}
    source: SourceRef     # name, url, retrieved_at, license
    assumptions: list[str]# every default we injected, spelled out
    warnings: list[str]   # e.g. "lat/lon >20mi from nearest NSRDB cell"
```

**Design rule:** never silently default. If the tool assumed `losses=14%`, say so in
`assumptions`. This is what makes results agent-trustworthy.

### Config & secrets
- Env vars only: `NREL_API_KEY`, `EIA_API_KEY`, `OPENEI_API_KEY`, `AHJ_REGISTRY_TOKEN`,
  `GOOGLE_MAPS_API_KEY` (optional adapter)
- `solar-mcp doctor` CLI: checks which keys are present, pings each source, prints setup
  links for missing ones

### Error taxonomy
- `SourceUnavailable` (5xx/timeouts) → tool returns partial result + warning, never crashes
- `QuotaExceeded` → returns cache if present, else actionable message
- `BadInput` → pydantic validation errors surfaced with the exact field and allowed range

## MCP design conventions

- Tool names: `verb_noun` (`estimate_production`, `lookup_tariffs`)
- Every tool docstring includes: what it does, when to use it vs. siblings, 1 worked
  example, units
- Prefer fewer, richer tools over many thin ones
- Read-only by default; anything that writes (cache sync) is clearly named `sync_*`
- Each server also exposes MCP *resources*: `source://<name>/license`,
  `source://<name>/coverage` so agents can cite provenance

---

# Phase 1 — nrel-solar server

## Scope

Wraps the NREL Developer Network solar APIs behind one free API key.

- **PVWatts v8** — production modeling (bifacial option, albedo, monthly irradiance
  losses, 2020 TMY NSRDB weather). Docs: https://developer.nlr.gov/docs/solar/pvwatts/v8/
- **Solar Resource / NSRDB** — irradiance statistics for a location.
  Docs: https://developer.nlr.gov/docs/solar/nsrdb/
- Rate limit: 1,000 requests/hour — mitigated by 30-day HTTP cache

## Tools

### estimate_production

```
estimate_production(
  lat: float, lon: float,
  system_capacity_kw: float,           # 0.05–500000
  tilt_deg: float | None = None,       # default: latitude, stated in assumptions
  azimuth_deg: float = 180,
  array_type: Literal["fixed_open","fixed_roof","1axis","1axis_backtrack","2axis"] = "fixed_roof",
  module_type: Literal["standard","premium","thin_film"] = "standard",
  losses_pct: float = 14.0,
  bifacial: bool = False,
  albedo: float | None = None,
  dc_ac_ratio: float = 1.2,
) -> ToolResult  # data: ac_annual_kwh, ac_monthly, capacity_factor, solrad_annual
```

### compare_orientations
Sweeps tilt × azimuth grid (bounded to ≤25 PVWatts calls, cache-aware), returns ranked
table + % delta vs. optimum. Answers "how bad is my north-facing roof really?"

### get_solar_resource
Annual/monthly GHI, DNI, resolved NSRDB cell, distance warning if far from query point.

> **Deviation from original spec (verified 2026-07-05):** the Solar Resource v1 API does
> not return resolved-cell coordinates. The tool computes the 0.1° grid-cell center
> locally and states that in `assumptions`. The ">32 km" distance warning applies to
> PVWatts `station_info.distance` (meters, optional in response), which the API does return.

### size_system_for_target
Inverse solve: target annual kWh → required kW (search over cached PVWatts calls,
≤6 iterations).

## Implementation notes

- Validate all params to PVWatts documented ranges *before* the HTTP call — return
  `BadInput` with allowed range
- Surface PVWatts' own caveat verbatim in `warnings`: model estimates don't reflect
  site-specific shading or module-level differences
- `station_info.distance > 32 km` → warning
- Ship `examples/claude_desktop_config.json` and a 60-second demo:
  *"Compare annual production for an 8 kW system in Mesa AZ at 10° vs 25° tilt"*

## Definition of done (v0.1)

- [x] 4 tools above, typed envelope, assumptions populated
- [x] Fixture tests: 100% of tools, zero live calls in CI
- [x] `solar-mcp doctor` validates NREL key
- [x] README quickstart ≤ 5 minutes to first result
- [ ] Published to PyPI + submitted to MCP registries (manual release step)

---

# Testing, CI & release engineering

## Fixture-first (no live calls in CI)

- `fixtures/<source>/<tool_case>.json`: recorded real responses, scrubbed of keys
- Recorder: `pytest --record` hits live APIs (local only, needs keys) and refreshes
  fixtures; CI runs replay-only
- Contract tests: pydantic-validate every fixture against our response models — catches
  upstream schema drift when fixtures are re-recorded

## Test pyramid per server

1. **Unit** — pure logic (math, normalization, conversions): no mocks
2. **Tool tests** — MCP tools against fixture-backed client; assert envelope completeness
3. **Smoke (nightly, live)** — 1 real call per source with a repo secret key (post-v0.1)
4. **Agent eval (pre-release)** — scripted prompts, grader checks units + source cited

## CI (GitHub Actions)

- Matrix: py3.11/3.12 × {lint, typecheck, test}
- `uv` for install; ruff + mypy strict gate
- Coverage floor 85% on core + Phase 1
- Release: tag → build → publish changed packages to PyPI

## Release checklist (every version)

- [ ] Fixtures re-recorded within 30 days
- [ ] `solar-mcp doctor` passes against live sources
- [ ] Demo prompt transcript updated in README
- [ ] MCP registry listings updated

---

# Data source registry (Phase 1 sources)

| Source | What | Access | Auth | Limits/Notes |
|---|---|---|---|---|
| PVWatts v8 | Production modeling | REST | Free NREL key | 1,000 req/hr shared across NREL APIs; 429 on exceed; rolling window |
| NSRDB / Solar Resource | Irradiance | REST | Same NREL key | Same key/limits; 0.1° cells |

Full registry (Phases 2–4 sources, link index) lives in the Notion sub-page
"Data Source Registry".

---

# Phase 2 — solar-economics server (SHIPPED)

Tools: `lookup_tariffs` (URDB v8, normalized flat/tiered view, TOU flagged not
simulated), `get_electricity_prices` (EIA v2 state averages + trend),
`get_incentives` (hardcoded federal ITC table per 26 USC §25D with citation +
DSIRE snapshot programs with vintage), `sync_incentives` (bulk loader), and the
composite `estimate_roi`: estimate_production (library import) → tariff (EIA
fallback with state=XX) → ITC → 25-year cash flow (payback/NPV/IRR) with a
per-component audit trail. Financial math is pure (`economics.py`), tested
against hand-computed cases. Always warns "screening estimate".

Install cost default: Tracking the Sun state median when a snapshot is synced
(Phase 3), else a cited national median constant.

# Phase 3 — solar-market server (SHIPPED)

Bulk tier: `sync_tracking_the_sun` (streams multi-GB CSVs into DuckDB, column
mapping validated, optional state filter) and `sync_solartrace` — the only
writers. Query tools: `query_installed_systems` (aggregates only; median $/W,
size quartiles, top equipment), `get_permitting_timelines` (SolarTRACE medians
by state/jurisdiction), `find_utility_scale_projects` (USPVDB PostgREST API —
filter syntax `p_state=eq.CO`, no auth), `identify_ahj` (SunSpec registry,
token via support@sunspec.org; degrades into setup instructions without one),
`market_snapshot` (best-effort composite with audit trail). Every bulk-backed
result cites its snapshot vintage.

# Phase 4 — solar-forecast server (SHIPPED)

`forecast_generation` (hourly kW series ≤48h) and `compare_forecast_to_model`
(forecast vs PVWatts TMY spread uniformly over the month's hours — the
simplification is stated in assumptions; non-24h-multiple horizons warn).

> **Dependency deviation:** quartz-solar-forecast pins pydantic==2.6.2, which
> conflicts with the MCP SDK — it is NOT a declared dependency. The model sits
> behind a Predictor seam (lazy import + install instructions; tests stub it;
> CI never loads the ML stack). Install steps in the package README.

# Excluded from this build

google-solar adapter (optional, bring-your-own-key, requires GCP billing —
CLAUDE.md keeps it out of scope unless requested), PVDAQ, TOU tariff
simulation, REopt (all deferred to v2 by the roadmap).
