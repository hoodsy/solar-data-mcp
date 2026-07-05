---
name: solar-quote-review
description: Audit an installer's quote against market prices, modeled production, and the incentive schedule. Use when the user has a bid or quote in hand and asks whether it is fair, realistic, or worth signing.
tools: query_installed_systems, estimate_production, estimate_roi, get_incentives
---

# Quote review

The audit counterpart to solar-site-assessment: check someone else's numbers
instead of generating fresh ones. Extract from the quote: system size (kW),
total price or $/W, promised annual kWh, promised payback, claimed incentives,
and module/equipment tier if stated.

## Workflow

1. **Price check** — `query_installed_systems(state, year_start=<recent>)` and
   place the quote's $/W against the returned median and p25/p75 spread.
   Requires a Tracking the Sun snapshot (solar-data-sync); if none is synced,
   say the only anchor is the national 3.0 $/W constant rather than implying a
   real comparison happened.
2. **Production check** — `estimate_production` mirroring the quote's actual
   specs: capacity, `module_type` (use `premium` if the quote names
   high-efficiency panels), and the real roof tilt/azimuth. Compare to the
   promised kWh.
3. **Payback check** — `estimate_roi` with `install_cost_usd` set to the quote
   total and `state` set. Compare payback/NPV against the sales pitch.
4. **Incentive check** — `get_incentives(state, install_year)`. Verify the
   claimed federal ITC percentage against the schedule (30% through 2032, 26%
   in 2033, 22% in 2034, 0% from 2035) and flag any state incentive the quote
   nets that our ROI deliberately does not.

## Sharp edges

- Compare gross to gross: quotes usually state pre-incentive prices, and
  `median_price_per_watt` from Tracking the Sun is pre-incentive too.
- The snapshot lags the market — cite its vintage. Installed prices trend
  down, so a quote slightly under an old median is normal, not suspicious.
- A production promise 10–15% above your PVWatts estimate deserves a question
  about assumed losses or premium modules; mirror those in
  `estimate_production` before calling it inflated.
- Verdicts are screening-grade: frame findings as questions for the installer
  ("ask why their production figure assumes X"), not accusations.

## Reporting

Present a per-claim table: quoted value, modeled/market value, verdict.
Surface every assumption behind your side of the comparison, per
solar-data-conventions.

## Report template

When the user wants the review as a document, render exactly this shape:

```
# Quote review: <system size> at <location>
<date> · quote from <installer, if named>

## Verdict table   — claim | quoted | modeled/market | verdict
                     (price $/W, production kWh/yr, payback yrs, incentives)
## Evidence        — one short subsection per claim: how the check was run,
                     which assumptions were mirrored from the quote, source +
                     vintage of the market anchor
## Questions for your installer — one per flagged claim, phrased neutrally
## Assumptions & caveats — verbatim envelope assumptions/warnings; note if
                     the price anchor was the national constant (no TTS sync)
```

Verdicts are one of: "in line", "worth a question", "outlier". Never render
an accusation; the document's job is to arm a conversation.
