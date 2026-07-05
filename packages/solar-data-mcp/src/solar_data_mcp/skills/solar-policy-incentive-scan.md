---
name: solar-policy-incentive-scan
description: Compare solar incentive landscapes across states and against the federal ITC schedule. Use for "which states have the best incentives", "what can I claim in state X this year", or ITC timing questions.
tools: sync_incentives, get_incentives
---

# Policy & incentive scan

Federal ITC comes from current law and is always available; state and local
programs come from a DSIRE snapshot that must be synced first.

## Workflow

1. Ensure a DSIRE snapshot: if `get_incentives` warns it is returning
   federal-only, run `sync_incentives(source=<DSIRE program export>)` per
   solar-data-sync, then re-query.
2. `get_incentives(state, install_year)` per state of interest.
3. Compare program counts and types across states; note administrator
   diversity (utility programs vs state agencies) as a robustness signal.
4. Frame federal timing with the ITC schedule: 30% through 2032, 26% in 2033,
   22% in 2034, 0% from 2035 — "install before 2033" is the only deadline
   current law imposes.

## Sharp edges

- Programs are *listed, not valued*: the tools do not compute a dollar figure
  for state programs, so never invent one. Count and categorize instead.
- Without a DSIRE sync the answer silently narrows to federal-only — a
  warning says so; surface it rather than presenting federal-only as the full
  landscape.
- Cite the DSIRE snapshot vintage; programs open and close faster than most
  datasets refresh.
- For "what is this worth to me" follow-ups, hand off to
  solar-site-assessment — `estimate_roi` nets the federal ITC and lists the
  rest.

## Reporting

Per solar-data-conventions: vintage cited, warnings surfaced, no invented
dollar values.
