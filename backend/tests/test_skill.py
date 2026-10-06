"""The `swolemates` skill served at skill://swolemates/* (app/mcp/skill.py)."""

import json
import re
from pathlib import Path

from app.mcp import skill as skill_module
from app.mcp.server import mcp


async def test_skill_main_file_is_listed_with_its_description() -> None:
    resources = await mcp.list_resources()

    by_uri = {str(r.uri): r for r in resources}
    skill = by_uri.get("skill://swolemates/SKILL.md")
    assert skill is not None
    # The frontmatter description is what a host sees before deciding to read the
    # skill — it has to say what the skill is for.
    assert "workout and nutrition tracker" in (skill.description or "")


async def test_skill_body_names_the_look_first_tools() -> None:
    result = await mcp.read_resource("skill://swolemates/SKILL.md")

    text = result.contents[0].content
    assert "get_goals" in text
    assert "get_progress" in text
    # Logging etiquette: canonical names and real macros, not guesses.
    assert "search_exercises" in text
    assert "search_food_facts" in text
    # The detail lives in a supporting doc so reading the skill itself stays cheap
    # (PR #35 review) — the body must point at it.
    assert "references/tool-shapes.md" in text


async def test_tool_shapes_reference_is_served() -> None:
    """Exercises SkillProvider's supporting-file template path. Deliberately doesn't
    pin the #31/#32/#33 workaround wording — that text should go away when those
    issues are fixed, not be defended by a test."""
    result = await mcp.read_resource("skill://swolemates/references/tool-shapes.md")

    assert "## log_workout" in result.contents[0].content


# Backticked snake_case identifiers in the skill docs that are *not* tool names —
# argument/field names the docs quote bare. Anything else that looks like
# `snake_case` (or a `## snake_case` heading) is taken to be a tool reference.
NON_TOOL_IDENTIFIERS = {"next_time_note", "set_number", "coach_notes"}

_SKILL_DIR = Path(skill_module.__file__).parent / "skills" / "swolemates"
_FENCED = re.compile(r"```.*?```", re.DOTALL)
_TOOLISH = re.compile(r"`([a-z]+(?:_[a-z]+)+)`|^#+\s+([a-z]+(?:_[a-z]+)+)\s*$", re.M)


def _referenced_tool_names() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for doc in [_SKILL_DIR / "SKILL.md", *sorted((_SKILL_DIR / "references").glob("*.md"))]:
        text = _FENCED.sub("", doc.read_text())
        for m in _TOOLISH.finditer(text):
            name = m.group(1) or m.group(2)
            if name not in NON_TOOL_IDENTIFIERS:
                found.setdefault(name, set()).add(doc.name)
    return found


def _is_model_visible(tool) -> bool:
    visibility = ((tool.meta or {}).get("ui") or {}).get("visibility")
    return visibility is None or "model" in visibility


async def test_every_tool_the_skill_names_is_a_model_visible_tool() -> None:
    """Catches a renamed/removed tool, a typo, or the skill pointing the model at an
    app-only tool it can't call. A new non-tool identifier in the docs belongs in
    NON_TOOL_IDENTIFIERS."""
    tools = {t.name: t for t in await mcp.list_tools()}
    referenced = _referenced_tool_names()
    assert "log_workout" in referenced  # the extraction is actually finding things

    unknown = {n: docs for n, docs in referenced.items() if n not in tools}
    assert not unknown, f"skill names tools the server doesn't register: {unknown}"
    hidden = sorted(n for n in referenced if not _is_model_visible(tools[n]))
    assert not hidden, f"skill names app-only tools the model can't call: {hidden}"


async def test_skill_manifest_lists_all_files() -> None:
    result = await mcp.read_resource("skill://swolemates/_manifest")

    manifest = json.loads(result.contents[0].content)
    assert manifest["skill"] == "swolemates"
    paths = {f["path"] for f in manifest["files"]}
    assert {"SKILL.md", "references/tool-shapes.md"} <= paths
