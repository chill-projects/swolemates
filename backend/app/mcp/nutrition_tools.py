"""Nutrition tools — core slice only (#4). log_nutrition is plain text for now; it
gets bound to ui://swolemates/nutrition-day.html once that component exists (a later
slice). get_goals/set_goals stay text-only permanently, per claude-tools-v1.md §3.4.
"""

from contextlib import asynccontextmanager

from app.auth import mcp_user_sub
from app.db import get_sessionmaker
from app.mcp.server import mcp
from app.services import nutrition as service


@asynccontextmanager
async def tool_session():
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@mcp.tool
async def log_nutrition(
    entries: list[dict], name: str | None = None, meal_type: str | None = None
) -> str:
    """Record one or more trackable entries — a meal, a glass of water, creatine — in one call.

    Args:
        entries: [{"trackable_key": "calories", "value": 450}, ...]. Valid keys today:
            calories, protein_g, carbs_g, fat_g, fiber_g.
        name: What was logged, e.g. "chicken and rice".
        meal_type: breakfast/lunch/dinner/snack, if applicable.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        log = await service.log_nutrition(
            session, user_sub, entries=entries, name=name, meal_type=meal_type, source="manual"
        )
        totals = ", ".join(f"{e['trackable_key']}={e['value']}" for e in entries)
        return f"Logged {log.name or 'entry'}: {totals}."


@mcp.tool
async def get_goals() -> str:
    """Read the caller's current nutrition goals."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        goals = await service.get_goals(session, user_sub)
        if not goals:
            return "No goals set yet."
        return ", ".join(f"{g.trackable_key}: {g.target_value}" for g in goals)


@mcp.tool
async def set_goals(goals: list[dict]) -> str:
    """Set or update any subset of nutrition goals in one call.

    Args:
        goals: [{"trackable_key": "calories", "target_value": 2200, "is_streak_target": true}, ...].
            is_streak_target is optional; at most one goal can carry it — setting it on
            one clears it from any other.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        updated = await service.set_goals(session, user_sub, goals=goals)
        return ", ".join(f"{g.trackable_key}: {g.target_value}" for g in updated)
