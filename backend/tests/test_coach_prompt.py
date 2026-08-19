from app.mcp import nutrition_tools, workouts_tools
from app.mcp.server import mcp


def test_log_workout_docstring_carries_the_always_on_coaching_nudge() -> None:
    assert "last time" in workouts_tools.log_workout.__doc__


def test_finish_workout_docstring_carries_the_always_on_coaching_nudge() -> None:
    assert "last time" in workouts_tools.finish_workout.__doc__


def test_log_nutrition_docstring_carries_the_always_on_coaching_nudge() -> None:
    assert "last time" in nutrition_tools.log_nutrition.__doc__


async def test_coach_prompt_is_registered() -> None:
    prompt = await mcp.get_prompt("coach")

    assert prompt is not None


async def test_coach_prompt_renders_text_naming_the_tools_it_calls_first() -> None:
    prompt = await mcp.get_prompt("coach")

    result = await prompt.render()

    text = result.messages[0].content.text
    assert "get_goals" in text
    assert "get_progress" in text
