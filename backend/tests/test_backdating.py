"""Backdating is a capability, not a module: it spans the nutrition tools, the workout
tools, and the coach prompt, and it broke in the seam between them. The service layer
always took `logged_at`; the MCP tool layer just never passed it, so the same write
worked over REST and was impossible from chat — and log_nutrition's docstring told the
model outright that there was "no backdating param here", which is what users heard
back as "I can't log a previous day".

These are signature and text assertions rather than behaviour tests on purpose. The
behaviour lives in test_nutrition_logs.py / test_workouts.py / test_planned_workouts.py;
what this file guards is that the model-facing surface still *offers* it.
"""

import inspect
from collections.abc import Callable

import pytest

from app.mcp import nutrition_tools, workouts_tools
from app.mcp.coach_prompt import COACH_PROMPT_TEXT
from app.mcp.server import mcp

# Every tool a user could reasonably be mid-sentence with when they realize the day
# they mean is not today.
BACKDATABLE = [
    nutrition_tools.log_nutrition,
    nutrition_tools.log_meal_template,
    nutrition_tools.get_nutrition_day,
    nutrition_tools.update_nutrition_log,
    nutrition_tools.amend_last_log,
    workouts_tools.log_workout,
    workouts_tools.log_activity,
    workouts_tools.update_workout,
]


def _ids(fns: list[Callable]) -> list[str]:
    return [fn.__name__ for fn in fns]


@pytest.mark.parametrize("tool", BACKDATABLE, ids=_ids(BACKDATABLE))
def test_tool_takes_an_optional_date(tool: Callable) -> None:
    parameter = inspect.signature(tool).parameters.get("date")

    assert parameter is not None, f"{tool.__name__} has no way to name a day"
    assert parameter.default is None, f"{tool.__name__}'s date must be optional"


@pytest.mark.parametrize("tool", BACKDATABLE, ids=_ids(BACKDATABLE))
def test_tool_documents_its_date(tool: Callable) -> None:
    """An undocumented param is one the model won't reach for — the failure mode here
    was never a missing capability so much as a surface that didn't advertise one."""
    assert "date:" in (tool.__doc__ or ""), f"{tool.__name__} doesn't document date"


def test_log_nutrition_no_longer_tells_the_model_backdating_is_impossible() -> None:
    assert "no backdating param" not in (nutrition_tools.log_nutrition.__doc__ or "")


async def test_the_registered_tool_schemas_expose_date() -> None:
    """Signatures are what the code sees; the input schema is what the model sees. They
    can drift — a tool re-registered through a wrapper that drops kwargs would still
    pass the signature check above."""
    for name in ("log_nutrition", "log_workout", "get_nutrition_day"):
        schema = (await mcp.get_tool(name)).parameters
        assert "date" in schema["properties"], f"{name}'s schema hides date"
        assert "date" not in schema.get("required", []), f"{name}'s date must stay optional"


def test_coach_prompt_tells_the_model_to_backfill_a_missed_day() -> None:
    assert "date" in COACH_PROMPT_TEXT
    assert "log_nutrition" in COACH_PROMPT_TEXT
    assert "timezone" in COACH_PROMPT_TEXT
