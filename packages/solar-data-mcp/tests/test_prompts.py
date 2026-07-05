"""Prompt tests: user-facing entry points stay wired to real skills and
render the caller's inputs into the expansion text."""

import pytest
from solar_data_mcp.prompts import PROMPT_SKILLS
from solar_data_mcp.server import create_server
from solar_data_mcp.skills import load_skills

EXPECTED_PROMPTS = {"market_brief", "site_assessment", "quote_review", "proposal_builder"}

PROMPT_ARGS = {
    "market_brief": {"state": "TX"},
    "site_assessment": {"location": "Easton, PA", "annual_usage_or_bill": "9000 kWh"},
    "quote_review": {"quote_details": "7 kW for $21,000 in Denver"},
    "proposal_builder": {"customer_details": "Austin, 14000 kWh, south roof, $2.60/W"},
}


def test_prompt_catalog_is_complete() -> None:
    assert set(PROMPT_SKILLS) == EXPECTED_PROMPTS
    assert set(PROMPT_ARGS) == EXPECTED_PROMPTS


def test_every_prompt_targets_a_real_report_skill() -> None:
    skills = {skill.name: skill for skill in load_skills()}
    for prompt_name, skill_name in PROMPT_SKILLS.items():
        assert skill_name in skills, f"{prompt_name} targets unknown skill {skill_name!r}"
        assert "## Report template" in skills[skill_name].text, (
            f"{prompt_name} targets {skill_name}, which has no report template"
        )


@pytest.mark.anyio
async def test_prompts_listed_with_descriptions() -> None:
    server = create_server()
    prompts = {prompt.name: prompt for prompt in await server.list_prompts()}
    assert set(prompts) == EXPECTED_PROMPTS
    for prompt in prompts.values():
        assert prompt.description
        assert {arg.name for arg in prompt.arguments or []} == set(PROMPT_ARGS[prompt.name])


@pytest.mark.anyio
async def test_prompt_expansion_references_skill_and_inputs() -> None:
    server = create_server()
    for prompt_name, arguments in PROMPT_ARGS.items():
        result = await server.get_prompt(prompt_name, arguments)
        text = result.messages[0].content.text  # type: ignore[union-attr]
        assert f"skill://solar/{PROMPT_SKILLS[prompt_name]}" in text
        assert "skill://solar/solar-data-conventions" in text
        assert "Report template" in text
        for value in arguments.values():
            assert value in text, f"{prompt_name} expansion drops input {value!r}"
