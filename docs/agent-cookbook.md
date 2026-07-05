# Agent cookbook

Prompts that show what the suite can do once the servers are configured
(see `examples/claude_desktop_config.json`).

## Production & siting (nrel-solar)
1. "Compare annual production for an 8 kW system in Mesa, AZ at 10° vs 25° tilt."
2. "How bad is a north-facing roof in Seattle, really? Sweep the orientations."
3. "My home in Denver uses 9,000 kWh a year — what size system covers it?"
4. "How sunny is Duluth compared to Albuquerque?" (GHI/DNI via get_solar_resource)

## Economics (solar-economics)
5. "What are Xcel's residential rate schedules in Boulder, and which are time-of-use?"
6. "How have Colorado residential electricity prices trended over the last year?"
7. "What solar incentives can I claim in Arizona this year?"
8. "Would a 6 kW system pay off at my house (39.74, -105.18)? I pay cash, state CO."
   — the flagship: estimate_roi returns payback/NPV/IRR plus the full audit trail;
   ask "what did you assume?" and read the assumptions list back.

## Market intelligence (solar-market)
9. "Sync the Tracking the Sun file I downloaded and tell me the median $/W in CO since 2022."
10. "How long does solar permitting take in Denver vs Phoenix?" (needs SolarTRACE sync)
11. "List the five biggest solar farms in Colorado and whether they have batteries."
12. "Give me a one-shot market snapshot for Texas."

## Forecast (solar-forecast)
13. "How much will my 6 kW system in Boulder produce tomorrow?"
14. "Is today an unusually good solar day at my site?" (compare_forecast_to_model)

## Cross-server
15. "Estimate ROI for the biggest viable rooftop system in Austin, then check
    whether this week's weather makes it a good time to start measuring."

Every answer carries `units`, a `source` citation, `assumptions` (every default
the tools injected), and `warnings` — ask the agent to show them when a number
matters.
