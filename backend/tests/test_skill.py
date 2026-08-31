"""The `swolemates` skill served at skill://swolemates/* (app/mcp/skill.py)."""

import json

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


async def test_tool_shapes_reference_covers_the_connector_papercuts() -> None:
    """The shapes doc exists for issues #31 (log_workout item key), #33 (substring
    search retry strategy), and #32 (update_workout can't append sets). Reading it
    also exercises SkillProvider's supporting-file template path."""
    result = await mcp.read_resource("skill://swolemates/references/tool-shapes.md")

    text = result.contents[0].content
    assert '"exercise"`, not `"name"' in text
    assert "contiguous" in text
    assert "cannot append" in text


async def test_skill_manifest_lists_all_files() -> None:
    result = await mcp.read_resource("skill://swolemates/_manifest")

    manifest = json.loads(result.contents[0].content)
    assert manifest["skill"] == "swolemates"
    paths = {f["path"] for f in manifest["files"]}
    assert {"SKILL.md", "references/tool-shapes.md"} <= paths
