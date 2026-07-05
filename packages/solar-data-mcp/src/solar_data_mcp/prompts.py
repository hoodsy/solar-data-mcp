"""MCP prompts: user-facing entry points to the report-shaped skills.

Skills route agents by question shape; prompts let a *user* pick a deliverable
from their host's UI (Claude Desktop / Claude Code surface these natively) and
parameterize it. Each prompt expands to the same instruction: load the skill,
run its workflow for the given inputs, render its report template. Nothing is
duplicated — the skill file stays the single source of procedure.
"""

from mcp.server.fastmcp import FastMCP

# prompt name -> skill name; tests cross-check both directions.
PROMPT_SKILLS = {
    "market_brief": "solar-market-brief",
    "site_assessment": "solar-site-assessment",
    "quote_review": "solar-quote-review",
    "proposal_builder": "solar-proposal-builder",
}


def _expand(skill: str, task: str) -> str:
    return (
        f"Read the resource skill://solar/{skill} and follow it exactly: run its "
        f"Workflow for the inputs below, honor its Sharp edges, and render its "
        f"Report template as the final answer (including the assumptions and "
        f"data-gap sections). Also apply skill://solar/solar-data-conventions.\n\n"
        f"{task}"
    )


def register(mcp: FastMCP) -> None:
    @mcp.prompt(
        name="market_brief",
        title="Solar market brief",
        description="Standardized state solar-market report: adoption, pricing, policy, "
        "utility-scale infrastructure, permitting friction.",
    )
    def market_brief(state: str) -> str:
        return _expand("solar-market-brief", f"State to brief: {state}")

    @mcp.prompt(
        name="site_assessment",
        title="Solar site assessment",
        description="Would solar pay off here? Sizing, production, incentives, and "
        "screening ROI for one location.",
    )
    def site_assessment(location: str, annual_usage_or_bill: str) -> str:
        return _expand(
            "solar-site-assessment",
            f"Location: {location}\nAnnual usage or bill: {annual_usage_or_bill}",
        )

    @mcp.prompt(
        name="quote_review",
        title="Solar quote review",
        description="Audit an installer's quote against market prices, modeled "
        "production, and the incentive schedule.",
    )
    def quote_review(quote_details: str) -> str:
        return _expand(
            "solar-quote-review",
            "Quote to review (size, price, promised production/payback, location): "
            f"{quote_details}",
        )

    @mcp.prompt(
        name="proposal_builder",
        title="Solar proposal builder",
        description="Turn a customer address, usage, roof planes, and your cost basis "
        "into a full proposal package.",
    )
    def proposal_builder(customer_details: str) -> str:
        return _expand(
            "solar-proposal-builder",
            "Customer inputs (location, annual kWh, roof planes, cost per watt): "
            f"{customer_details}",
        )
