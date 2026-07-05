"""Agent skills: procedural instructions served as MCP resources.

Tools are capability; skills are procedure. Each *.md file in this package
teaches an agent how to orchestrate the tools for one shape of question —
tool ordering, sync prerequisites, defaults to override, reporting rules.
skill://solar/index is the routing table: the server instructions point hosts
at it, and hosts with a native skill concept can lift the frontmatter
descriptions directly.

Frontmatter is deliberately minimal (name, description, tools as one
comma-separated line) so it parses without a YAML dependency while remaining
valid YAML for hosts that repackage skills as plugins.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from importlib import resources

from mcp.server.fastmcp import FastMCP

INDEX_URI = "skill://solar/index"

_INDEX_PREAMBLE = """\
Solar skill routing table.

Skills are procedures: each teaches the tool ordering, sync prerequisites,
defaults to override, and reporting rules for one shape of question. Route by
what is being asked, never by who is asking — a homeowner, an installer, and
an analyst asking the same question get the same skill.

How to route:
1. Match the question against the descriptions below and read that
   skill://solar/<name> resource before calling tools.
2. Always apply skill://solar/solar-data-conventions — the contract for
   reading every tool's result envelope (assumptions, warnings, provenance).
3. If a tool fails with "snapshot not synced", switch to
   skill://solar/solar-data-sync, run the named sync, then resume.

Skills:
"""


@dataclass(frozen=True)
class Skill:
    """One parsed *.md skill file; text is the full raw file, served as-is."""

    name: str
    description: str
    tools: tuple[str, ...]
    text: str


def parse_skill(stem: str, text: str) -> Skill:
    """Parse frontmatter; strict, so a malformed skill fails at load, not at read."""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError(f"skill {stem}: file must start with '---' frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise ValueError(f"skill {stem}: unterminated frontmatter") from None
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"skill {stem}: bad frontmatter line {line!r}")
        fields[key.strip()] = value.strip()
    name = fields.get("name", "")
    description = fields.get("description", "")
    if not name or not description:
        raise ValueError(f"skill {stem}: frontmatter must set name and description")
    if name != stem:
        raise ValueError(f"skill {stem}: frontmatter name {name!r} does not match filename")
    tools = tuple(tool.strip() for tool in fields.get("tools", "").split(",") if tool.strip())
    return Skill(name=name, description=description, tools=tools, text=text)


def load_skills() -> list[Skill]:
    skills_dir = resources.files(__name__)
    return [
        parse_skill(entry.name.removesuffix(".md"), entry.read_text(encoding="utf-8"))
        for entry in sorted(skills_dir.iterdir(), key=lambda entry: entry.name)
        if entry.name.endswith(".md")
    ]


def build_index(skills: Sequence[Skill]) -> str:
    entries = "\n".join(f"- skill://solar/{s.name} — {s.description}" for s in skills)
    return _INDEX_PREAMBLE + entries + "\n"


def register(mcp: FastMCP) -> None:
    skills = load_skills()

    @mcp.resource(INDEX_URI, title="Solar skills: routing table")
    def index() -> str:
        return build_index(skills)

    for skill in skills:
        _register_one(mcp, skill)


def _register_one(mcp: FastMCP, skill: Skill) -> None:
    # Separate function so the closure binds this skill, not the loop variable.
    @mcp.resource(f"skill://solar/{skill.name}", title=f"Skill: {skill.name}")
    def read_skill() -> str:
        return skill.text
