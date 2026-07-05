---
name: solar-market-brief
description: Produce a standardized state solar-market brief — adoption, pricing, policy, utility-scale infrastructure, permitting friction. Use for "brief me on the X solar market" or any single-geography market overview.
tools: market_snapshot, query_installed_systems, get_electricity_prices, get_incentives, find_utility_scale_projects, get_permitting_timelines
---

# Market brief

A repeatable five-section brief for one state. Sync snapshots first if needed
(solar-data-sync); the brief degrades gracefully without them but says so.

## Workflow

Start from `market_snapshot(state)` as the skeleton, then enrich each section:

1. **Adoption** — `query_installed_systems` over successive year windows
   (`year_start`/`year_end`) for volume trend.
2. **Pricing** — the same calls' median $/W and p25–p75 spread, framed against
   `get_electricity_prices(state)` retail levels and trend.
3. **Policy** — `get_incentives(state)`: federal ITC status plus state/local
   programs (needs the DSIRE snapshot for the latter — a warning tells you
   when you are seeing federal-only).
4. **Infrastructure** — `find_utility_scale_projects(state=..., limit=5)`:
   top plants by capacity, battery colocation share, build years.
5. **Friction** — `get_permitting_timelines(state=...)`: median permit,
   inspection, and PTO days.

Close with a one-paragraph synthesis: what makes this market distinctive.

## Sharp edges

- `market_snapshot` sections that could not run arrive as warnings — name
  what is missing ("no SolarTRACE snapshot synced") instead of silently
  shrinking the brief.
- Composite results carry real per-component provenance in
  `data.audit_trail`; the top-level source is a placeholder. Cite from the
  audit trail.
- Coverage honesty: Tracking the Sun and SolarTRACE are substantial but
  incomplete — absence is not evidence; report `system_count` alongside any
  percentile.

## Reporting

Every section cites source + vintage, per solar-data-conventions.
