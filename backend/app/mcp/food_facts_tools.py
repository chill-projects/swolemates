"""Food-facts lookup over Open Food Facts.

Renders in the nutrition-day UI (`ui://swolemates/nutrition-day.html`) as a search
panel — pick a match there and it calls `log_nutrition` directly, same as a manual
entry. Also plain-callable from chat: the `matches` list is model-readable JSON, so
Claude can read the numbers straight into a `log_nutrition` call without a UI at all.
"""

from fastmcp.apps import AppConfig

from app.mcp._resources import NUTRITION_UI_URI
from app.mcp.server import mcp
from app.services import food_facts as service


@mcp.tool(app=AppConfig(resource_uri=NUTRITION_UI_URI, visibility=["model", "app"]))
async def search_food_facts(query: str | None = None, barcode: str | None = None) -> dict:
    """Look up nutrition facts from Open Food Facts, by free-text query or barcode.

    Provide exactly one of `query` or `barcode`; if both are given, `barcode` wins.
    Each match reports calories, protein_g, carbs_g, fat_g, fiber_g per the serving OFF
    describes (falling back to per-100g, noted per match) — read those numbers straight
    into a `log_nutrition` call rather than re-deriving them.

    Args:
        query: Free-text product search, e.g. "plain greek yogurt".
        barcode: A product barcode (EAN/UPC), e.g. "3017620422003".
    """
    try:
        matches = await service.search_food_facts(query=query, barcode=barcode)
    except ValueError as exc:
        return {"matches": [], "error": str(exc)}
    return {"matches": matches}
