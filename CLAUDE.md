# CLAUDE.md — solar-data-mcp

Open-source monorepo of MCP servers making US open solar data agent-accessible.
Full spec: docs/SPEC.md. Build ONE phase at a time; current target: **Phase 1 (nrel-solar)**.

## Commands
- Install: `uv sync`
- Test (fixtures only, no live calls): `uv run pytest`
- Record fixtures (needs keys in .env): `uv run pytest --record`
- Lint/type: `uv run ruff check . && uv run mypy --strict`
- Key check: `uv run solar-mcp doctor`

## Architecture rules
- uv workspace: `packages/core` (shared) + one package per server (`packages/nrel-solar`, ...)
- Every tool returns the `ToolResult` envelope from core: data + units + source + assumptions + warnings
- NEVER silently default a parameter — every injected default goes in `assumptions`
- All HTTP goes through core's client (retry, token-bucket rate limit, SQLite cache). NREL limit: 1,000 req/hr
- Validate inputs with pydantic BEFORE any HTTP call; errors must name the field and allowed range
- Tool names: verb_noun. Docstrings: purpose, when-to-use-vs-siblings, one worked example, units

## Testing rules
- CI makes ZERO live API calls — replay fixtures from `fixtures/<source>/`
- Pure logic (economics math, normalization) gets plain unit tests, no mocks
- Coverage floor: 85% on core + nrel-solar

## Style
- Python 3.11+, mypy --strict clean, ruff clean
- MIT license headers not required; keep files small and single-purpose

## Out of scope (do not build unless asked)
- Phases 2–4, PVDAQ, TOU tariff simulation, REopt, any web UI
- Google Solar adapter (optional package, later; never a core dependency)

## Definition of done — Phase 1 v0.1
- [ ] Tools: estimate_production, get_solar_resource, compare_orientations, size_system_for_target
- [ ] Fixture tests for all tools; envelope completeness asserted
- [ ] `solar-mcp doctor` validates NREL key
- [ ] README quickstart ≤5 min to first result
- [ ] Publishable to PyPI (build passes); Claude Desktop config example in examples/