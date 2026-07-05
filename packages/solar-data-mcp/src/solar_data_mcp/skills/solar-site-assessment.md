---
name: solar-site-assessment
description: Evaluate whether solar pays off at a specific location — sizing, production, tariffs, incentives, and ROI end to end. Use when someone asks "should I go solar", "would an X kW system pay off here", or "what size system covers my usage".
tools: get_electricity_prices, size_system_for_target, estimate_production, lookup_tariffs, get_incentives, estimate_roi
---

# Site assessment

The end-to-end "should I go solar" workflow. For auditing a quote someone else
produced, use solar-quote-review instead; for a full installer proposal with
orientation options, use solar-proposal-builder.

## Workflow

1. Resolve the site to lat/lon and a two-letter state. Both are needed
   throughout; never proceed on a city name alone.
2. Establish annual consumption in kWh. If the user only knows a dollar bill,
   convert with `get_electricity_prices(state)` — annual kWh ≈ annual dollars /
   average rate — and state that conversion as an assumption in your answer.
3. `size_system_for_target(lat, lon, target_annual_kwh)` for the coverage size
   (costs at most 6 PVWatts calls, converges to 2%).
4. If the user described their roof (tilt, direction, shading, array type),
   call `estimate_production` with those explicit values. Skip this only when
   no roof details were given.
5. Context calls: `lookup_tariffs(lat, lon)` for the rate landscape and
   `get_incentives(state, install_year)` for the full incentive list.
6. `estimate_roi(lat, lon, system_capacity_kw, state=...)` — always pass
   `state`. Pass `install_cost_usd` OR `cost_per_watt` if the user has a real
   number (never both), and `annual_consumption_kwh` when known.
7. Report payback, NPV, and IRR, then read the `assumptions` list back to the
   user before they act on the numbers.

## Sharp edges

- `estimate_roi` does NOT accept tilt/azimuth/array_type/losses. It models
  production internally with all defaults (tilt = |lat|, azimuth 180, fixed
  roof, 14% losses). If the user gave roof geometry, compare your explicit
  `estimate_production` result against the ROI's internal one (in
  `data.audit_trail`) and flag the delta.
- Without `state`, a TOU-only tariff result makes `estimate_roi` fail. With
  `state`, the EIA state-average fallback works, and a synced Tracking the Sun
  snapshot upgrades the cost basis from the flat national 3.0 $/W to the state
  median (see solar-data-sync).
- State/local incentives are listed in the result but NOT netted from the
  cost. Never subtract them again; present them as "potential additional
  savings".
- TOU tariffs are flagged (`is_tou`) but never simulated. Say so if the user
  is on one.

## Reporting

Every ROI figure is screening-grade — keep the screening caveat attached, cite
sources from `data.audit_trail`, and follow solar-data-conventions.
