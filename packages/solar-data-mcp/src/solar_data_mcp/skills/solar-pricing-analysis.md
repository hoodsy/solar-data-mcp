---
name: solar-pricing-analysis
description: Analyze residential installed solar prices — $/W levels, trends over time, and spreads — from Tracking the Sun, framed against retail electricity prices. Use for "what happened to installed prices in X", "where is pricing softest", or any $/W question.
tools: query_installed_systems, get_electricity_prices
---

# Pricing analysis

$/W analytics from the Tracking the Sun snapshot. Requires a synced snapshot
(solar-data-sync); for cross-state comparisons the snapshot must have been
loaded without a state filter.

## Workflow

1. **Trend** — call `query_installed_systems(state, year_start, year_end)`
   over successive windows (e.g. 2019–2021, then 2022–vintage) and compare
   medians.
2. **Spread** — the p25–p75 range within one window is a maturity and
   competition signal: tight spreads suggest a commoditized installer market,
   wide spreads suggest room to shop.
3. **Cross-state** — repeat per state and rank.
4. **Value framing** — pair with `get_electricity_prices(state)`: "installed
   $/W is falling while retail rates rise" is the value-proposition headline
   when both hold.

## Sharp edges

- Prices are self-reported to LBNL and the snapshot lags the market — always
  cite the vintage and the year window next to any figure.
- Aggregates only: the tool never returns row-level systems. Do not promise
  individual records.
- A thin `system_count` makes percentiles noisy — report the count alongside
  the stats and decline to rank states whose counts differ by orders of
  magnitude without saying so.
- Size percentiles (`size_kw_p25/median/p75`) shift over time too — a $/W
  drop can partly reflect larger systems, not cheaper installs; mention size
  drift when it is material.

## Reporting

Per solar-data-conventions: vintage + source with every number, warnings
surfaced verbatim.
