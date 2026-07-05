---
name: solar-performance-check
description: Forecast a system's next-48-hour output or judge whether its recent production is normal. Use for "what will my system make tomorrow", "is today unusually good/bad for solar", or "my system produced X kWh — is that right?".
tools: forecast_generation, compare_forecast_to_model, estimate_production
---

# Performance check

Three question shapes, three paths. All need the system's lat/lon, capacity,
and ideally tilt/azimuth (defaults: tilt = |lat|, azimuth 180 — say so when
you rely on them).

## Workflow

- **Future** ("tomorrow", "this weekend"): `forecast_generation(lat, lon,
  capacity_kw, horizon_hours=...)`. Horizon is capped at 48 hours — decline
  longer windows rather than extrapolating. Report total kWh, peak kW, and
  peak time.
- **Today vs typical** ("is today unusually good?"):
  `compare_forecast_to_model` — a ratio ≥115% of the TMY baseline reads
  "unusually sunny", ≤85% "below typical", between is "close to typical".
- **Past month** ("my June statement shows 780 kWh — normal?"): compare the
  actual figure against `estimate_production`'s `ac_monthly` entry for that
  month, using the system's real specs.

## Sharp edges

- TMY is a *typical* year, not this year's weather. One low month is weather
  until proven otherwise — do not diagnose equipment failure from a single
  data point. Suggest checking whether `compare_forecast_to_model` has also
  been reading low on clear days.
- For systems more than a few years old, apply ~0.5%/yr degradation (the same
  rate the ROI math uses) before calling a shortfall real.
- The Quartz model is an optional install (its pydantic pin conflicts with
  the MCP SDK). If the forecast tools return an install-instructions error,
  relay those steps to the user verbatim — a persistent install is required;
  ephemeral `uvx` environments cannot hold it.
- The baseline comparison spreads a month's TMY production uniformly across
  its hours (a stated assumption); partial-day horizons carry a warning.

## Reporting

Forecasts are screening-grade, never grid-settlement or trading data. Keep
the open-model caveat attached and follow solar-data-conventions.
