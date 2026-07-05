# CLAUDE.md — solar-data-mcp

Open-source monorepo of MCP servers making US open solar data agent-accessible.
Full spec: docs/SPEC.md. All four phases are built: nrel-solar, solar-economics,
solar-market, solar-forecast. Work one phase/package at a time; keep every gate green.

## Commands
- Install: `uv sync`
- Test (fixtures only, no live calls): `uv run pytest`
- Record fixtures (needs keys in .env): `uv run pytest --record`
- Lint/type: `uv run ruff check . && uv run mypy --strict`
- Key check: `uv run solar-data-mcp doctor`

## Architecture rules
- uv workspace: `packages/core` (shared) + one package per server (`packages/nrel-solar`, ...)
  + `packages/solar-data-mcp` (umbrella: all four servers' tools on one stdio entry; the
  user-facing install — PyPI's `solar-mcp` name belongs to an unrelated project)
- Every tool returns the `ToolResult` envelope from core: data + units + source + assumptions + warnings
- NEVER silently default a parameter — every injected default goes in `assumptions`
- All HTTP goes through core's client (retry, token-bucket rate limit, SQLite cache). NREL limit: 1,000 req/hr
- Validate inputs with pydantic BEFORE any HTTP call; errors must name the field and allowed range
- Tool names: verb_noun. Docstrings: purpose, when-to-use-vs-siblings, one worked example, units

## Testing rules
- CI makes ZERO live API calls — replay fixtures from `fixtures/<source>/`
- Pure logic (economics math, normalization) gets plain unit tests, no mocks
- Coverage floor: 85% across all packages (enforced in CI via --cov flags)

## Style
- Python 3.11+, mypy --strict clean, ruff clean
- MIT license headers not required; keep files small and single-purpose

## Out of scope (do not build unless asked)
- PVDAQ, TOU tariff simulation, REopt, any web UI (deferred to v2 by the roadmap)
- Google Solar adapter (optional package, later; never a core dependency)

## Definition of done — every change
- [x] Phase 1–4 tools shipped with fixture tests and envelope completeness asserted
- Gates for any new work: `uv run pytest` green (replay only), ruff + mypy --strict clean,
  coverage ≥85% (CI), fixtures scrubbed of keys, every injected default in `assumptions`
- Release steps that remain manual: PyPI upload (core + domain packages BEFORE
  solar-data-mcp, or `uvx solar-data-mcp` cannot resolve), MCP registry listings, demo GIF