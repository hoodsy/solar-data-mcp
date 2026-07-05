"""Skill layer tests: the routing index, per-skill resources, and the drift
guards that keep skill files honest against the real tool surface."""

import pytest
from solar_data_mcp.server import INSTRUCTIONS, create_server
from solar_data_mcp.skills import INDEX_URI, build_index, load_skills, parse_skill

# The canonical catalog. Hard-coded so a deleted or renamed skill file fails
# here instead of silently shrinking the resource list.
EXPECTED_SKILLS = {
    "solar-site-assessment",
    "solar-quote-review",
    "solar-performance-check",
    "solar-proposal-builder",
    "solar-territory-expansion",
    "solar-market-brief",
    "solar-pricing-analysis",
    "solar-utility-scale-scout",
    "solar-policy-incentive-scan",
    "solar-data-sync",
    "solar-data-conventions",
}


def test_catalog_is_complete() -> None:
    assert {skill.name for skill in load_skills()} == EXPECTED_SKILLS


def test_frontmatter_contract() -> None:
    for skill in load_skills():
        assert skill.description, f"{skill.name} has no description"
        assert len(skill.description) <= 320, f"{skill.name}: description too long to route on"
        assert "Use " in skill.description, f"{skill.name}: description lacks a routing trigger"
        # Every skill except the conventions contract orchestrates tools.
        if skill.name != "solar-data-conventions":
            assert skill.tools, f"{skill.name} lists no tools"


@pytest.mark.anyio
async def test_skill_tools_exist_on_server() -> None:
    """Drift guard: every tool a skill claims to orchestrate must be a real
    tool on the umbrella server, and must actually appear in the skill body."""
    server = create_server()
    tool_names = {tool.name for tool in await server.list_tools()}
    for skill in load_skills():
        for tool in skill.tools:
            assert tool in tool_names, f"{skill.name} references unknown tool {tool!r}"
            # Bodies write tools as `tool_name` or `tool_name(args)`.
            assert f"`{tool}" in skill.text, f"{skill.name} never mentions its tool {tool!r}"


def test_index_routes_every_skill() -> None:
    index = build_index(load_skills())
    for name in EXPECTED_SKILLS:
        assert f"skill://solar/{name} — " in index, f"index missing {name}"
    # The three routing rules: match by question, always-load conventions, sync recovery.
    assert "who is asking" in index
    assert "skill://solar/solar-data-conventions" in index
    assert "skill://solar/solar-data-sync" in index


def test_instructions_point_at_index() -> None:
    assert INDEX_URI in INSTRUCTIONS


@pytest.mark.anyio
async def test_skill_resources_served_verbatim() -> None:
    server = create_server()
    for skill in load_skills():
        contents = list(await server.read_resource(f"skill://solar/{skill.name}"))
        assert contents[0].content == skill.text
    index = list(await server.read_resource(INDEX_URI))
    assert index[0].content == build_index(load_skills())


def test_parse_skill_rejects_malformed_frontmatter() -> None:
    good = "---\nname: x\ndescription: d\ntools: a, b\n---\nbody\n"
    parsed = parse_skill("x", good)
    assert parsed.tools == ("a", "b")
    assert parsed.text == good

    with pytest.raises(ValueError, match="must start with"):
        parse_skill("x", "no frontmatter\n")
    with pytest.raises(ValueError, match="unterminated"):
        parse_skill("x", "---\nname: x\n")
    with pytest.raises(ValueError, match="bad frontmatter line"):
        parse_skill("x", "---\nname x\n---\n")
    with pytest.raises(ValueError, match="name and description"):
        parse_skill("x", "---\nname: x\n---\n")
    with pytest.raises(ValueError, match="does not match filename"):
        parse_skill("y", "---\nname: x\ndescription: d\n---\n")
