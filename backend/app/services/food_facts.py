"""Food-facts lookup — a pure proxy/normalizer over Open Food Facts, no DB, no AI call.

Barcode lookups hit OFF's API v3 (`/api/v3/product/{barcode}.json`); text search hits
Search-a-licious (`https://search.openfoodfacts.org/search`). Both return product-shaped
JSON with a `nutriments` dict keyed like `proteins_serving` / `proteins_100g`; this module
normalizes either shape into the five `trackable_key` fields the `log_nutrition` tool
expects: calories, protein_g, carbs_g, fat_g, fiber_g — always **per 100g**, so a caller
(the UI's grams input, or Claude in chat) can scale by however many grams the person
actually portioned out, kitchen-scale style, rather than by a manufacturer's serving.

`_build_client` is the seam tests replace with an `httpx.MockTransport` — no real network
call happens in the test suite.
"""

import re

import httpx

USER_AGENT = "Swolemates/1.0 (https://github.com/chill-projects/swolemates)"
BARCODE_URL_TEMPLATE = "https://world.openfoodfacts.org/api/v3/product/{barcode}.json"
SEARCH_URL = "https://search.openfoodfacts.org/search"

# OFF nutriment key -> our output field.
_NUTRIMENT_FIELDS = {
    "calories": "energy-kcal",
    "protein_g": "proteins",
    "carbs_g": "carbohydrates",
    "fat_g": "fat",
    "fiber_g": "fiber",
}

# A leading gram quantity in OFF's freeform serving_size string ("15 g", "1 bar (40g)"),
# not preceded by a letter (so it doesn't match the "g" in "mg") and not followed by one
# (so it doesn't match "g" inside a longer unit word). Used only to prefill the UI's
# grams input — the actual math below never depends on this parsing succeeding.
_GRAMS_RE = re.compile(r"(?<![a-zA-Z])(\d+(?:\.\d+)?)\s*g\b", re.IGNORECASE)


def _build_client() -> httpx.AsyncClient:
    """OFF's usage policy requires a compliant User-Agent on every request."""
    return httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=10.0)


def _parse_serving_grams(serving_size: object) -> float | None:
    if not isinstance(serving_size, str):
        return None
    match = _GRAMS_RE.search(serving_size)
    return float(match.group(1)) if match else None


def _normalize_product(raw: dict) -> dict:
    nutriments = raw.get("nutriments") or {}
    serving_grams = _parse_serving_grams(raw.get("serving_size"))

    values: dict[str, float | None] = {}
    for field, off_key in _NUTRIMENT_FIELDS.items():
        per_100g = nutriments.get(f"{off_key}_100g")
        if isinstance(per_100g, int | float):
            values[field] = per_100g
            continue
        # Some products only ever get `_serving` data contributed — convert it to the
        # per-100g basis everything else uses, when the serving size is actually in
        # grams (not "1 cup" or similar, which can't be converted this way).
        per_serving = nutriments.get(f"{off_key}_serving")
        if isinstance(per_serving, int | float) and serving_grams:
            values[field] = per_serving / serving_grams * 100
        else:
            values[field] = None

    brands = raw.get("brands")
    brand = ", ".join(brands) if isinstance(brands, list) else (brands or None)

    return {
        "name": raw.get("product_name") or raw.get("product_name_en") or "Unknown product",
        "brand": brand,
        "serving_grams": serving_grams,
        **values,
    }


async def _lookup_barcode(client: httpx.AsyncClient, barcode: str) -> list[dict]:
    resp = await client.get(BARCODE_URL_TEMPLATE.format(barcode=barcode))
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    data = resp.json()
    product = data.get("product")
    if not product or data.get("status") == "failure":
        return []
    return [_normalize_product(product)]


async def _search_by_query(client: httpx.AsyncClient, query: str, *, limit: int = 10) -> list[dict]:
    resp = await client.get(SEARCH_URL, params={"q": query, "page_size": limit})
    resp.raise_for_status()
    hits = resp.json().get("hits") or []
    return [_normalize_product(hit) for hit in hits]


async def search_food_facts(*, query: str | None = None, barcode: str | None = None) -> list[dict]:
    """Look up nutrition facts by barcode or free-text query.

    Exactly one of `query`/`barcode` is expected; if both are given, `barcode` wins
    (it's the unambiguous identifier). Returns a list of normalized matches — empty,
    never an exception, when OFF has nothing.
    """
    barcode = barcode.strip() if barcode else None
    query = query.strip() if query else None
    if not barcode and not query:
        raise ValueError("Provide a query or a barcode.")

    async with _build_client() as client:
        if barcode:
            return await _lookup_barcode(client, barcode)
        return await _search_by_query(client, query)
