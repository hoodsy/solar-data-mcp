---
name: solar-utility-scale-scout
description: Survey utility-scale PV plants by state or bounding box — capacity, batteries, tracking type, build years — and screen greenfield sites. Use for questions about solar farms, large-scale development, or what is built in an area.
tools: find_utility_scale_projects, get_solar_resource, identify_ahj
---

# Utility-scale scout

Ground-mounted utility-scale PV from USPVDB — live and keyless, no sync
needed. Rooftop and small commercial live in Tracking the Sun instead (see
solar-pricing-analysis).

## Workflow

1. `find_utility_scale_projects` with exactly one of `state` or
   `bbox=[west, south, east, north]`; optionally `min_capacity_mw`. Results
   come largest-first, `limit` up to 100.
2. Summarize the landscape: total capacity, battery colocation share
   (`has_battery`), tracking mix (`p_axis`: fixed vs single-axis), and build
   years for pipeline momentum.
3. **Greenfield screening**: for a candidate area, pair the bbox query (who
   is already there) with `get_solar_resource` at the area's centroid (annual
   GHI/DNI) — strong resource plus existing interconnected projects is a
   positive signal.
4. `identify_ahj(lat, lon)` for the jurisdiction lead when permitting context
   matters.

## Sharp edges

- USPVDB covers ground-mounted utility-scale only — never present its totals
  as "all solar in the state".
- `bbox` order is [west, south, east, north]; a reversed box returns a
  validation error naming the field — fix and retry once.
- `identify_ahj` needs the email-issued AHJ_REGISTRY_TOKEN and returns leads,
  not filings-grade facts — verify with the county before anything binding.
- Capacity comes as both AC and DC (`capacity_mw_ac`/`capacity_mw_dc`) —
  say which one you are quoting; rankings use AC.

## Reporting

Cite USPVDB (USGS) and retrieval date per solar-data-conventions.
