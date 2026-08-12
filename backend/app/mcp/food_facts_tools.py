"""Food-facts lookup — a single text-only MCP tool over Open Food Facts.

No `ui://` component here: this tool exists to feed a later `log_nutrition` call (a
different, not-yet-built slice), so the output is task-shaped text a model can read
straight into that call's arguments, not a rendered widget.
"""

from app.mcp.server import mcp
from app.services import food_facts as service

_MACRO_FIELDS = ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g")


def _format_match(match: dict) -> str:
    header = match["name"]
    if match.get("brand"):
        header += f" ({match['brand']})"
    macros = ", ".join(
        f"{field}={match[field] if match[field] is not None else 'unknown'}"
        for field in _MACRO_FIELDS
    )
    return f"- {header} — {match['serving_description']}: {macros}"


@mcp.tool
async def search_food_facts(query: str | None = None, barcode: str | None = None) -> str:
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
        return str(exc)

    if not matches:
        return "No matches found."

    return "\n".join(_format_match(m) for m in matches)
