---
name: solar-territory-expansion
description: Compare candidate states or metros on electricity rates, installed prices, permitting friction, incentives, and solar resource. Use for "where should we expand next" or any side-by-side geography comparison for solar operators.
tools: market_snapshot, get_electricity_prices, query_installed_systems, get_permitting_timelines, get_incentives, get_solar_resource
---

# Territory expansion

Comparative geography analysis: N candidate markets in, one comparison table
out. Sync snapshots once before starting (solar-data-sync) — one sync serves
every candidate. Skip the Tracking the Sun `state` filter here: a filtered
store can only answer for one state.

## Workflow

Run `market_snapshot(state)` per candidate as the first pass, then fill the
comparison table dimension by dimension:

- **Customer value** — `get_electricity_prices(state)`: rate level and trend.
  Higher and rising retail rates strengthen the pitch.
- **Competitive landscape** — `query_installed_systems(state, year_start=...)`:
  median $/W (pricing headroom) and system_count (activity).
- **Friction** — `get_permitting_timelines(state=...)`: median permit +
  inspection + PTO days across jurisdictions.
- **Demand drivers** — `get_incentives(state)`: program count and types.
- **Production potential** — `get_solar_resource(lat, lon)` at a
  representative point per market: annual GHI.

Assemble one row per candidate; every figure carries its source vintage.

## Sharp edges

- Tracking the Sun coverage varies by state — compare `system_count` values
  *relative* to each other, never as absolute market size.
- Absence of a jurisdiction in SolarTRACE is not evidence of no market (it
  covers ~65% of US residential installs).
- `market_snapshot` is best-effort: sections it could not run arrive as
  warnings. Report which sections were skipped instead of presenting a
  partial snapshot as complete.
- Rank explicitly and state the weighting you used — "Phoenix wins on rates
  and friction, Salt Lake on incentives" beats an unexplained score.

## Reporting

Cite each dataset's vintage next to its column, per solar-data-conventions.
