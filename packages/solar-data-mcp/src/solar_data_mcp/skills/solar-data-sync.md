---
name: solar-data-sync
description: Load or refresh the local Tracking the Sun, SolarTRACE, and DSIRE snapshots that several query tools require. Use when a tool fails with "snapshot not synced" or before market, pricing, or incentive work.
tools: sync_tracking_the_sun, sync_solartrace, sync_incentives
---

# Data sync

Three datasets are bulk files, not live APIs. Each `sync_*` tool loads an
export into a local store and stamps it with a `vintage`; query tools then
read the store offline. A query tool that needs a missing snapshot fails with
an error naming the exact sync to run — run it and retry, don't apologize.

## The three loaders

| Sync tool | Unlocks | Notes |
|---|---|---|
| `sync_tracking_the_sun` | `query_installed_systems`; upgrades `estimate_roi` cost basis to the state median $/W | LBNL release is 1–2 GB |
| `sync_solartrace` | `get_permitting_timelines` | jurisdiction-level medians |
| `sync_incentives` | state/local rows in `get_incentives` | DSIRE program export |

## Workflow

1. Each loader accepts `source=` as a local file path or an `http(s)` URL
   (URLs are streamed to a temp file, never held in memory).
2. Pass `vintage=` as the dataset's release date when you know it; it
   defaults to today, and every downstream figure cites it.
3. `sync_tracking_the_sun` takes an optional `state=` filter to shrink the
   store. Use it for single-state work; skip it when cross-state comparisons
   are coming (a filtered store answers only for that state).
4. Everything lands in one shared DuckDB
   (`~/.cache/solar-data-mcp/bulk.duckdb`, relocatable via
   SOLAR_DATA_MCP_CACHE_DIR) — a Tracking the Sun sync done for market work
   also improves every later `estimate_roi` call.

## Sharp edges

- Loads are stage-validate-swap: a failed load leaves the previous snapshot
  intact, and the error names the missing or malformed columns.
- Re-sync on the datasets' release cadence (Tracking the Sun is roughly
  annual); a stale vintage is fine as long as it is cited.
- The loaders accept either the canonical columns or the raw LBNL layout for
  Tracking the Sun; sentinel values (−9999) and non-positive rows are
  filtered during load.

## Reporting

After a sync, report `rows_loaded` and `vintage`, then resume the original
question.
