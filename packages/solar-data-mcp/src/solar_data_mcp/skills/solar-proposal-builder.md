---
name: solar-proposal-builder
description: Turn a customer address, usage, roof planes, and a real installed cost into a full proposal — size, orientation options, production, ROI, incentive appendix, permitting expectations. Use for installer sales workflows building a customer package.
tools: size_system_for_target, compare_orientations, estimate_production, estimate_roi, get_incentives, identify_ahj, get_permitting_timelines
---

# Proposal builder

Input shape: customer location, annual usage (kWh), available roof planes
(each plane = one azimuth + tilt), and the company's real cost per watt.
Output shape: a proposal package with a design, production figure, economics,
incentive appendix, and a "what happens after you sign" expectations page.

## Workflow

1. `size_system_for_target(lat, lon, target_annual_kwh)` for the baseline
   size.
2. `compare_orientations` over the *actual roof planes*: pass each plane's
   azimuth and a coarse tilt grid. The tool caps at 25 tilt×azimuth
   combinations — sweep coarse first, then refine only around the winner in a
   second call. Rank options by `pct_delta_vs_best`.
3. `estimate_production` for the chosen design with the company's real
   `losses_pct` and `module_type`. This explicit run is the proposal's
   headline production number.
4. `estimate_roi` with `cost_per_watt` set to the company's actual cost and
   `state` set. Remember it models production internally with defaults — the
   proposal quotes production from step 3, economics from this step, and
   flags any material delta between the two.
5. `get_incentives(state, install_year)` for the appendix. Present state and
   local programs as "potential additional savings" — the ROI lists them but
   does not net them.
6. Expectations page: `identify_ahj(lat, lon)` to name the jurisdiction, then
   `get_permitting_timelines(jurisdiction=...)` for median permit,
   inspection, and PTO days.

## Sharp edges

- Budget the shared NREL quota: a full proposal flow can spend 25 sweep calls
  + 6 sizing calls + the ROI's internal production call from one 1,000 req/hr
  bucket (about 10 req/hr on DEMO_KEY). Coarse grids first; cached repeats
  are free.
- Never promise TOU arbitrage — TOU tariffs are flagged, not simulated.
- Permitting medians are historical and cover roughly 65% of US residential
  installs. Frame as "typical for this jurisdiction", never a commitment;
  absence of a jurisdiction is not evidence about it.
- `identify_ahj` needs the email-issued AHJ_REGISTRY_TOKEN and returns leads,
  not filings-grade facts. Without it, ask the customer's jurisdiction and
  query timelines by that name or by state.

## Reporting

Attach the assumption list to every number the customer will see, per
solar-data-conventions — a proposal that survives the customer's own
fact-check closes better.

## Report template

When the installer wants the customer package as a document, render exactly
this shape:

```
# Solar proposal: <customer location>
<date> · prepared for <customer> · <company cost basis: $X.XX/W>

## Design options  — table: plane | tilt | azimuth | kWh/yr | vs best (%)
## Recommended design — chosen plane(s), size (kW DC), production (kWh/yr)
                     from the explicit estimate_production run
## Economics       — table: gross cost | federal ITC | net cost | payback |
                     25-yr NPV, at the company's real cost basis
## Incentive appendix — federal line + state/local programs as "potential
                     additional savings" (not netted above)
## What happens after you sign — jurisdiction name; median permit /
                     inspection / PTO days, framed as "typical", with the
                     ~65% coverage caveat
## Assumptions appendix — the envelope's assumptions, verbatim
```

The production headline must come from the explicit `estimate_production`
run (step 3), never from the ROI's internal default-orientation model.
