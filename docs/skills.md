# Skill catalog

Status: **shipped**. The eleven skills below live in
`packages/solar-data-mcp/src/solar_data_mcp/skills/` and are served by the unified
`solar-data` server as MCP resources — `skill://solar/<name>` per skill, with
`skill://solar/index` as the routing table. This doc records the catalog's design
rationale; the skill files themselves are the operational source of truth.

## Skills vs tools

The MCP server provides **capability**: eighteen tools with schemas, validation, and the
`ToolResult` envelope. A skill provides **procedure**: a markdown instruction file an
agent loads into context that teaches *how to orchestrate* those tools — correct
ordering, sync prerequisites, which defaults to override, and how to report results
honestly. The tool docstrings answer "what does this tool do"; a skill answers "how do I
review a solar quote end to end without stepping on the sharp edges."

Two facts shape this catalog:

1. **One server.** `solar-data-mcp` (the umbrella package) serves all four domains'
   tools on a single stdio entry, so skills may assume the full toolset is always
   present. The sharing is load-bearing: one NREL client means one 1,000 req/hr token
   bucket drawn on by production, ROI, *and* forecast-vs-model tools, and one DuckDB
   handle backs every snapshot. Skills that chain heavy sweeps with ROI calls must
   budget accordingly.
2. **Distribution.** Skills ship *inside* the umbrella package
   (`packages/solar-data-mcp/src/solar_data_mcp/skills/*.md`) so the wheel always
   serves the skill version matching its tool signatures, exposed as MCP resources
   under `skill://solar/<name>` — the same pattern as `source://<name>/license`.
   Each file carries minimal YAML frontmatter (name, description, tools) so the set
   can be re-packaged as a Claude Code plugin later; never a separate repo — skills
   reference exact tool names and parameters and must change in lockstep with them
   (a test asserts every tool a skill names exists on the server).

## Routing

Routing is by **question shape, never by persona** — a homeowner, an installer, and an
analyst asking the same question get the same skill. Nobody declares who they are; the
persona tables below are a design/coverage lens, not a runtime concept. The mechanism,
in order of preference:

1. **Skill-native hosts** (Claude Code and similar) match the incoming question
   against each skill's frontmatter `description` — those descriptions are written as
   routing triggers ("Use when the user has a bid or quote in hand…").
2. **Plain MCP hosts** get pointed at the routing table by the server's
   `instructions`: "read `skill://solar/index` and load the matching
   `skill://solar/<name>` before multi-tool workflows." The index is generated from
   the frontmatter, so it cannot drift from the files.
3. Two standing routes hold regardless of entry point: `solar-data-conventions` is
   loaded alongside everything (envelope literacy), and any "snapshot not synced"
   error reroutes to `solar-data-sync`.

### Reports & prompts

The four deliverable-shaped skills (`site-assessment`, `quote-review`, `market-brief`,
`proposal-builder`) each carry a `## Report template` — a deterministic document shape
(section order, tables, where assumptions and vintages print) so every user asking the
same question gets the same report with their data in it. `solar-data-conventions`
adds an export convention for CSV-shaped output (unit-annotated headers from the
envelope's `units` map, provenance comment row).

The server also exposes four **MCP prompts** (`market_brief(state)`,
`site_assessment(location, annual_usage_or_bill)`, `quote_review(quote_details)`,
`proposal_builder(customer_details)`) — the user-facing entry: hosts surface them
natively (Claude Code: `/mcp__solar-data__market_brief`), and each expands to "load
the skill, run its workflow for these inputs, render its report template." Same skill
underneath; nothing duplicated. Tools stay presentation-free — the envelope is the
only tool output, and rendering is always the host's job.

## Personas

Three distinct users show up in the cookbook prompts, and they want different
workflows from the same tools:

| Persona | Cares about | Center of gravity |
|---|---|---|
| **Homeowner** (or homeowner-facing assistant) | Should I go solar? Is this quote fair? Is my system working? | `estimate_roi`, `estimate_production`, forecasts |
| **Installer** (sales & ops) | Fast credible proposals, where to expand, permitting expectations | sizing/sweeps + ROI with real costs, SolarTRACE, TTS pricing |
| **Analyst** (market/policy researcher, developer) | Market structure, pricing trends, policy landscape, utility-scale pipeline | TTS aggregates, USPVDB, EIA, DSIRE |

Plus a **cross-cutting** layer every persona's skills reference (envelope literacy,
snapshot ops).

### Persona × skill map

| Skill | Homeowner | Installer | Analyst |
|---|---|---|---|
| 1. solar-site-assessment | ● | ○ | |
| 2. solar-quote-review | ● | | |
| 3. solar-performance-check | ● | ○ | |
| 4. solar-proposal-builder | | ● | |
| 5. solar-territory-expansion | | ● | ○ |
| 6. solar-market-brief | | ○ | ● |
| 7. solar-pricing-analysis | | ○ | ● |
| 8. solar-utility-scale-scout | | | ● |
| 9. solar-policy-incentive-scan | | | ● |
| 10. solar-data-sync | (infra) | (infra) | (infra) |
| 11. solar-data-conventions | (infra) | (infra) | (infra) |

● primary audience · ○ secondary

---

## Homeowner skills

### 1. `solar-site-assessment` — the flagship

**Use when:** "Should I go solar?" / "Would a 6 kW system pay off at my house? I pay
cash, state CO." / "My home uses 9,000 kWh a year — what size covers it, and is it
worth it?" (cookbook #3, #7, #8, #15).

**Flow:** resolve location to lat/lon + state → if usage is known only as a dollar
bill, convert via `get_electricity_prices` state average (state that as an assumption)
→ `size_system_for_target` for the coverage size → if the user gave roof details, call
`estimate_production` with real tilt/azimuth/array_type → `lookup_tariffs` +
`get_incentives` for context → `estimate_roi` (always pass `state`) → read the
assumptions back to the user before they act on the number.

**Gotchas:**
- `estimate_roi` does **not** accept tilt/azimuth/array_type/losses — it runs
  production internally with all defaults (tilt = |lat|, azimuth 180, fixed roof, 14%
  losses). When the user specified roof geometry, run `estimate_production` separately
  and flag the delta.
- Always pass `state`: without it, a TOU-only URDB result fails the ROI; with it, the
  EIA fallback works and a synced Tracking the Sun snapshot upgrades cost from the
  flat national 3.0 $/W to the state median.
- At most one of `install_cost_usd` / `cost_per_watt`.
- State/local incentives are **listed but not netted** — never subtract them again.
- Surface the screening caveat with every ROI figure; TOU tariffs are flagged
  (`is_tou`) but never simulated.

### 2. `solar-quote-review` — "is this bid fair?"

**Use when:** the user has an installer's quote in hand — "$21,000 for a 7 kW system
that they say makes 11,000 kWh/yr and pays back in 8 years. Reasonable?" The audit
counterpart to site-assessment: it checks someone else's numbers instead of
generating fresh ones.

**Flow:**
1. **Price check** — `query_installed_systems(state, recent years)` and place the
   quote's $/W against the p25/median/p75 spread (needs a TTS sync; see skill 10).
2. **Production check** — `estimate_production` mirroring the quote's actual specs
   (capacity, module_type, roof tilt/azimuth) and compare to the promised kWh.
3. **Payback check** — `estimate_roi` with `install_cost_usd` set to the quote total
   and `state` set; compare payback/NPV to the sales pitch.
4. **Incentive check** — `get_incentives(state, install_year)`; verify the claimed ITC
   percentage against the schedule and flag any state incentive the quote nets that
   our ROI deliberately doesn't.

**Gotchas:**
- Compare gross to gross: quotes usually state pre-ITC prices, and TTS
  `median_price_per_watt` is pre-incentive too.
- The TTS snapshot lags the market (cite its `vintage`); installed prices trend down,
  so a quote slightly under an old median is normal, not suspicious.
- A production promise 10–15% above the PVWatts estimate deserves a question about
  assumed losses or premium modules — mirror those in `estimate_production` params
  before calling it inflated.
- Without a TTS sync the only price anchor is the national 3.0 $/W constant — say so
  rather than implying a real comparison happened.

### 3. `solar-performance-check` — "is my system doing what it should?"

**Use when:** "How much will my 6 kW system in Boulder produce tomorrow?" / "Is today
an unusually good solar day?" / "My June statement shows 780 kWh — is that normal?"
(cookbook #13–#14). Absorbs the earlier `solar-forecast-briefing` draft.

**Flow:** for the future, `forecast_generation` (≤48 h horizon); for "is today
unusual", `compare_forecast_to_model` (≥115% of the TMY baseline reads "unusually
sunny", ≤85% "below typical"); for a past month, compare the actual figure to
`estimate_production`'s `ac_monthly` for that month.

**Gotchas:**
- TMY is a *typical* year — a single bad month is weather until proven otherwise;
  don't diagnose equipment failure from one data point. Suggest checking whether the
  forecast-vs-model ratio has also been low.
- For systems more than a few years old, apply the 0.5%/yr degradation the ROI math
  uses before calling a shortfall real.
- Quartz is not a declared dependency (pydantic pin conflict) — if the forecast tools
  raise the install error, relay the INSTALL_HINT steps verbatim.
- Screening-grade, never grid-settlement; keep the open-model caveat attached.

---

## Installer skills

### 4. `solar-proposal-builder` — customer package in one pass

**Use when:** an installer-facing agent turns "customer at this address, 14,000 kWh/yr,
south and west roof planes, our cost is $2.60/W" into a proposal: system size, design
options, production, economics, incentive appendix, and a permitting expectation.

**Flow:** `size_system_for_target` from the customer's usage →
`compare_orientations` over the *actual roof planes* (each plane is one azimuth;
coarse tilt grid first — the 25-combination cap forces sweep discipline) →
`estimate_production` for the chosen design with the company's real loss figure →
`estimate_roi` with `cost_per_watt` set to the company's actual cost and `state` set →
`get_incentives` for the proposal appendix → `identify_ahj` +
`get_permitting_timelines(jurisdiction)` for the "what happens after you sign"
expectations page.

**Gotchas:**
- Everything in skill 1 about `estimate_roi`'s internal defaults applies double here:
  the proposal's headline production number must come from the explicit
  `estimate_production` run, not the ROI's internal one.
- Budget the shared NREL bucket: a full proposal flow is up to 25 sweep calls + 6
  sizing calls + the ROI's internal production call, all from one 1,000 req/hr quota
  (10/hr on DEMO_KEY). Coarse grids first; refine only the winning plane.
- Present state/local incentives as "potential additional savings," since the ROI
  lists but doesn't net them; never promise TOU arbitrage (flagged, not simulated).
- Permitting medians are historical and coverage-limited (~65% of US residential
  installs) — frame as "typical for this jurisdiction," not a commitment.

### 5. `solar-territory-expansion` — where to grow next

**Use when:** "We install in Colorado; should we open Phoenix or Salt Lake next?"
Comparative geography analysis for operators.

**Flow:** sync once (skill 10), then per candidate geography:
`get_electricity_prices` (rate level + trend = customer value proposition),
`query_installed_systems` ($/W landscape and volume), `get_permitting_timelines`
(friction/cycle time), `get_incentives` (demand drivers), `get_solar_resource`
(production potential); `market_snapshot` as the one-shot first pass. Assemble a
comparison table with every figure carrying its vintage.

**Gotchas:**
- TTS `system_count` is coverage-biased — compare volumes *relative* to each other,
  never as absolute market size; absence of a jurisdiction in SolarTRACE is not
  evidence of no market.
- `market_snapshot` is best-effort: sections that can't run arrive as warnings —
  report which were skipped instead of presenting a partial snapshot as complete.
- One sync serves all candidates (don't re-sync per state; the TTS `state` filter
  trades store size for multi-state comparisons — skip it here).

---

## Analyst skills

### 6. `solar-market-brief` — the standardized state brief

**Use when:** "Brief me on the Texas solar market" (cookbook #12). A repeatable
brief format: adoption, pricing, policy, infrastructure, friction.

**Flow:** `market_snapshot(state)` as the skeleton, then enrich each section:
`query_installed_systems` with year windows for adoption/pricing trend,
`get_electricity_prices` for the retail backdrop, `get_incentives` for policy,
`find_utility_scale_projects` (top 5, battery share) for infrastructure,
`get_permitting_timelines` for friction. Every section cites source + vintage;
composites' real provenance comes from `data.audit_trail`, not the top-level source.

**Gotchas:** sync prerequisites for the TTS/SolarTRACE/DSIRE sections (the snapshot
degrades gracefully — warnings name what's missing); coverage honesty per skill 11.

### 7. `solar-pricing-analysis` — $/W trends and spreads

**Use when:** "What's happened to residential installed prices in CO since 2019?" /
"Where is pricing softest?" (cookbook #9).

**Flow:** `query_installed_systems` over successive year windows (`year_start`/
`year_end`) to build a trend; use the p25–p75 spread as a maturity/competition
signal; compare states side by side; pair with `get_electricity_prices` to frame
value ("$/W is falling while retail rates rise").

**Gotchas:** TTS prices are self-reported and lag the market — always cite the
snapshot vintage and the year window; aggregates only (the tool never returns
row-level data, don't promise it); a thin `system_count` makes percentiles noisy —
report the count alongside the stats.

### 8. `solar-utility-scale-scout` — the big-iron landscape

**Use when:** "Five biggest solar farms in Colorado — do they have batteries?" /
"What's been built along this corridor?" (cookbook #11). Analysts and developers.
Promoted from a folded section: the developer/land-use audience is distinct enough
to deserve its own trigger.

**Flow:** `find_utility_scale_projects` by `state` or `bbox` (exactly one; limit ≤
100, largest first); summarize battery colocation share (`has_battery`), tracking
mix (`p_axis`), and build years for pipeline momentum; for greenfield screening,
pair a candidate `bbox` with `get_solar_resource` at its centroid; `identify_ahj`
for jurisdiction leads.

**Gotchas:** USPVDB is live and keyless — no sync needed; ground-mounted
utility-scale only (no rooftop/commercial — that's TTS's world); `identify_ahj`
needs the email-issued `AHJ_REGISTRY_TOKEN` and returns leads, not filings-grade
facts.

### 9. `solar-policy-incentive-scan` — the incentive landscape

**Use when:** "Which states have the richest solar incentives right now?" / "What can
I claim in Arizona this year?" (cookbook #7, for the research rather than purchase
angle).

**Flow:** `sync_incentives` once (skill 10) → `get_incentives(state, install_year)`
per state of interest → compare program counts and types; frame the federal timeline
with the ITC schedule (30% through 2032, 26% in 2033, 22% in 2034, 0% from 2035).

**Gotchas:** without a DSIRE sync the answer silently narrows to federal-only (a
warning says so — surface it); programs are *listed, not valued* — the tools don't
compute a dollar figure for state programs, so don't invent one; cite the DSIRE
snapshot vintage.

---

## Cross-cutting skills

### 10. `solar-data-sync` — snapshot operations

**Use when:** any skill above hits a `SourceUnavailable` naming a missing sync, or
on a schedule to keep snapshots fresh. Promoted to standalone now that three
personas depend on synced data (quote-review needs TTS as much as market-brief does).

**Teaches:**
- The three loaders and what each unlocks: `sync_tracking_the_sun` →
  `query_installed_systems` + `estimate_roi`'s state-median cost path;
  `sync_solartrace` → `get_permitting_timelines`; `sync_incentives` →
  `get_incentives` state/local data.
- Sources: each accepts a local file path or URL (streamed, never held in memory).
  The LBNL TTS release is 1–2 GB — pass the `state` filter for single-state work,
  skip it for cross-state comparisons.
- Everything lands in one shared DuckDB (`~/.cache/solar-data-mcp/bulk.duckdb`) with a
  `vintage` stamp — cite it with every derived figure; re-sync on the datasets'
  release cadence (TTS is roughly annual).

### 11. `solar-data-conventions` — envelope literacy

**Use when:** loaded alongside any other skill; the contract for reading and
reporting the `ToolResult` envelope.

**Reporting rules:** surface `assumptions` and `warnings` whenever a number matters;
cite `source.name` + `retrieved_at`; for composites (`estimate_roi`,
`market_snapshot`, `compare_forecast_to_model`) the top-level source is a placeholder
— real provenance is in `data.audit_trail`; a freshness warning means a stale cache
entry was served because quota ran out (real but old — say so); attribution text
lives in the `source://<name>/license` resources.

**Error recovery:** `BadInput` names the field and allowed range — correct and retry
once; `QuotaExceeded` — back off, 429s are never retried; `SourceUnavailable` — the
message names the fix (env var with signup URL, or the missing `sync_*`).

**Setup:** required keys (`NREL_API_KEY`, `OPENEI_API_KEY`, `EIA_API_KEY`; market and
forecast tools need none), `solar-data-mcp doctor` to verify, `SOLAR_DATA_MCP_CACHE_DIR`
to relocate the cache. DEMO_KEY reality: NREL allows it ~10 req/hr while the local
limiter assumes 1,000 — expect real 429s, and remember the bucket is now shared
across production, ROI, and forecast-vs-model tools on the unified server.

**What not to promise:** TOU simulation, REopt-style optimization, PVDAQ measured
data, non-US coverage — all deferred or out of scope per the SPEC. Decline gracefully
and name the closest tool family.

---

## Changes from the first draft

- `solar-forecast-briefing` → absorbed into `solar-performance-check` (the homeowner
  cares about their system; the forecast is the mechanism).
- `solar-system-design` → dissolved: sizing lives in `solar-site-assessment`,
  orientation sweeps in `solar-proposal-builder` (same tools, different persona
  framing).
- `solar-market-research` → split into `solar-market-brief`, `solar-pricing-analysis`,
  and `solar-data-sync` (the analyst persona turned out to be several workflows, and
  the sync dance serves everyone).
- `solar-utility-scale-scout` → promoted from a folded section (distinct audience).
- `solar-permitting-navigator` was considered and folded: AHJ + timeline lookup is a
  two-call sequence that lives naturally inside `solar-proposal-builder` and
  `solar-market-brief` rather than as its own trigger.

## Implementation notes

All eleven skills shipped together in
`packages/solar-data-mcp/src/solar_data_mcp/skills/`, registered by
`solar_data_mcp/skills/__init__.py` (frontmatter parser, index builder, resource
registration) and wired into `server.py` alongside the `source://` resources. Tests in
`packages/solar-data-mcp/tests/test_skills.py` pin the catalog (a deleted skill fails
CI), verify every tool a skill names exists on the real server and is mentioned in the
skill body, and assert the index and skill resources are served verbatim.
