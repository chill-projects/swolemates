"""TDEE calculator tool (#19, resolved) — text-only, no `ui://` component. A
one-time bootstrapping tool: used at onboarding to give an evidence-based starting
point for nutrition goals, re-runnable anytime on request, but it never silently
rewrites your goals on its own.
"""

from app.auth import mcp_user_sub
from app.mcp._adapter import catches_service_errors, tool_session
from app.mcp.server import mcp
from app.services import tdee as service


@mcp.tool
@catches_service_errors
async def calculate_targets() -> str:
    """Calculate calorie/macro targets from the caller's profile stats (sex, age,
    height, activity level, goal type — set via update_profile) and their most
    recently logged weight, using the Mifflin-St Jeor formula. Writes the result as
    normal goals via set_goals, so it's a solid, evidence-based starting point —
    fully editable afterward, and safe to re-run anytime stats or weight change.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        targets, tdee = await service.calculate_and_apply_targets(session, user_sub)
    return (
        f"Estimated TDEE: ~{round(tdee):,} cal/day. Set targets: {targets.calories:,} cal, "
        f"{targets.protein_g}g protein, {targets.carbs_g}g carbs, {targets.fat_g}g fat, "
        f"{targets.fiber_g}g fiber."
    )
