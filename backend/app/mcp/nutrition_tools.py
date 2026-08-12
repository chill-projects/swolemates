"""Nutrition tools (#4). log_nutrition and get_nutrition_day both render the day-vs-
goals view via ui://swolemates/nutrition-day.html — any call that changes today's
totals returns the full current picture, so the component re-renders from any result
without an extra round trip (the tmpx pattern). get_goals/set_goals stay text-only
permanently, per claude-tools-v1.md §3.4.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastmcp.apps import AppConfig

from app.auth import mcp_user_sub
from app.db import get_sessionmaker
from app.mcp.server import mcp
from app.services import nutrition as service

NUTRITION_UI_URI = "ui://swolemates/nutrition-day.html"

NUTRITION_UI_BUNDLE = (
    Path(__file__).resolve().parent.parent.parent / "static" / "mcp-apps" / "nutrition-day.html"
)


@asynccontextmanager
async def tool_session():
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _progress(tp: service.TrackableProgress) -> dict:
    return {
        "trackable_key": tp.trackable_key,
        "label": tp.label,
        "unit": tp.unit,
        "consumed": float(tp.consumed),
        "target": float(tp.target) if tp.target is not None else None,
    }


def _summary(day: service.NutritionDay) -> str:
    """'1,430 kcal so far, 96 g protein — 64 g to go', where the 'to go' figure tracks
    whichever goal is the streak target (the metric that actually matters for the
    user's stated aim) rather than always defaulting to calories."""
    parts = [f"{round(float(day.hero.consumed)):,} {day.hero.unit} so far"]
    parts += [f"{round(float(b.consumed))} {b.unit} {b.label.lower()}" for b in day.bars]
    text = ", ".join(parts)

    focus = (
        day.hero
        if day.streak_key in (None, "calories")
        else next((b for b in day.bars if b.trackable_key == day.streak_key), None)
    )
    if focus is not None and focus.target is not None:
        remaining = float(focus.target) - float(focus.consumed)
        if remaining >= 0:
            text += f" — {round(remaining):,} {focus.unit} to go"
        else:
            text += f" — {round(-remaining):,} {focus.unit} over"
    return text


async def _day_payload(session, user_sub: str) -> dict:
    day = await service.get_nutrition_day(session, user_sub)
    return {
        "date": day.date.isoformat(),
        "hero": _progress(day.hero),
        "bars": [_progress(b) for b in day.bars],
        "streak_key": day.streak_key,
        "logs": [
            {
                "id": str(log.id),
                "name": log.name,
                "logged_at": log.logged_at.isoformat(),
                "meal_type": log.meal_type,
                "values": {k: float(v) for k, v in log.values.items()},
            }
            for log in day.logs
        ],
        "summary": _summary(day),
    }


@mcp.tool(app=AppConfig(resource_uri=NUTRITION_UI_URI))
async def get_nutrition_day() -> dict:
    """Show today's nutrition so far against the caller's goals."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        return await _day_payload(session, user_sub)


@mcp.tool(app=AppConfig(resource_uri=NUTRITION_UI_URI, visibility=["model", "app"]))
async def log_nutrition(
    entries: list[dict], name: str | None = None, meal_type: str | None = None
) -> dict:
    """Record one or more trackable entries — a meal, a glass of water, creatine — in one call.

    Args:
        entries: [{"trackable_key": "calories", "value": 450}, ...]. Valid keys today:
            calories, protein_g, carbs_g, fat_g, fiber_g.
        name: What was logged, e.g. "chicken and rice".
        meal_type: breakfast/lunch/dinner/snack, if applicable.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        await service.log_nutrition(
            session, user_sub, entries=entries, name=name, meal_type=meal_type, source="manual"
        )
        return await _day_payload(session, user_sub)


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


@mcp.resource(NUTRITION_UI_URI)
def nutrition_day_ui() -> str:
    """The nutrition-day component — one bundle rendered by Claude and the SPA alike."""
    if NUTRITION_UI_BUNDLE.is_file():
        return NUTRITION_UI_BUNDLE.read_text()
    return (
        "<html><body style='font-family:system-ui;padding:1rem'>"
        "<p>The nutrition-day component bundle isn't built. Run <code>make apps</code>.</p>"
        "</body></html>"
    )
