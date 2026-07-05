---
name: solar-data-conventions
description: How to read and report every tool's result envelope — assumptions, warnings, provenance, error recovery, API keys, and quota. Use alongside every other solar skill; it is the contract the whole server follows.
tools:
---

# Data conventions

Every tool returns the same envelope: `data` + `units` + `source` +
`assumptions` + `warnings`. These rules apply to every workflow.

## Reporting rules

- When a number matters, surface its `assumptions` and `warnings` — every
  default the tools injected on the caller's behalf is listed there by
  design. A parameter you passed explicitly never appears.
- Cite `source.name` and `retrieved_at`. Units for any field are in `units`,
  keyed by field path (`ranked[].ac_annual_kwh`).
- Composites (`estimate_roi`, `market_snapshot`,
  `compare_forecast_to_model`) carry a placeholder top-level source; the real
  per-component provenance is in `data.audit_trail` — cite from there.
- A freshness warning means a stale cache entry was served because quota ran
  out: the number is real but old. Say so.
- License and attribution text for any dataset is served at
  `source://<name>/license`; coverage limits at `source://<name>/coverage`.

## Error recovery

- **Input errors** name the exact field and allowed range — correct the
  parameter and retry once.
- **Quota errors**: back off; the client never retries a 429, so hammering
  only burns the next hour's budget. Cached repeats of earlier calls are
  free.
- **Source-unavailable errors** name the fix: an unset env var (with its
  signup URL) or a missing `sync_*` prerequisite (see solar-data-sync).

## Setup

- Keys (all free): NREL_API_KEY (production, ROI, forecast-vs-model),
  OPENEI_API_KEY (tariffs), EIA_API_KEY (electricity prices);
  AHJ_REGISTRY_TOKEN is optional (email-issued). Market and forecast tools
  need no key. Verify with `solar-data-mcp doctor`.
- DEMO_KEY works for NREL at ~10 requests/hour — expect real 429s on sweeps,
  and note the one NREL quota is shared across production, ROI, and
  forecast-vs-model tools.
- The HTTP cache and bulk store live under `~/.cache/solar-data-mcp`
  (relocatable via SOLAR_DATA_MCP_CACHE_DIR).

## What not to promise

TOU tariff simulation, REopt-style optimization, PVDAQ measured production,
and non-US coverage are out of scope. Decline gracefully and name the closest
tool family instead of improvising.
