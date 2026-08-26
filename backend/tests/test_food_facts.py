import httpx
from httpx import AsyncClient

from app.services import food_facts as service


def _client_builder(handler):
    """A `_build_client` replacement wired to a MockTransport instead of the network."""

    def build_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), headers={})

    return build_client


async def test_barcode_lookup_normalizes_off_v3_response(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/product/3017620422003.json"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "product": {
                    "product_name": "Nutella",
                    "brands": "Nutella, Ferrero",
                    "serving_size": "15 g",
                    "nutriments": {
                        "energy-kcal_serving": 80,
                        "energy-kcal_100g": 539,
                        "proteins_serving": 0.9,
                        "proteins_100g": 6.3,
                        "carbohydrates_serving": 8.6,
                        "carbohydrates_100g": 57.5,
                        "fat_serving": 4.6,
                        "fat_100g": 30.9,
                        "fiber_serving": 0.5,
                        "fiber_100g": 3.4,
                    },
                },
            },
        )

    monkeypatch.setattr(service, "_build_client", _client_builder(handler))

    results = await service.search_food_facts(barcode="3017620422003")

    assert results == [
        {
            "name": "Nutella",
            "brand": "Nutella, Ferrero",
            "serving_grams": 15.0,
            "calories": 539,
            "protein_g": 6.3,
            "carbs_g": 57.5,
            "fat_g": 30.9,
            "fiber_g": 3.4,
        }
    ]


async def test_barcode_lookup_converts_serving_only_data_to_per_100g(
    monkeypatch,
) -> None:
    """A product contributed with only `_serving` nutriments (common on OFF) still
    needs to come through per-100g — converted using the gram serving size — so the
    UI's grams input can scale it like any other match."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "success",
                "product": {
                    "product_name": "Protein Bar",
                    "brands": "Acme",
                    "serving_size": "1 bar (40g)",
                    "nutriments": {
                        "energy-kcal_serving": 200,
                        "proteins_serving": 20,
                    },
                },
            },
        )

    monkeypatch.setattr(service, "_build_client", _client_builder(handler))

    results = await service.search_food_facts(barcode="0000000000001")

    assert results == [
        {
            "name": "Protein Bar",
            "brand": "Acme",
            "serving_grams": 40.0,
            "calories": 500.0,  # 200 / 40 * 100
            "protein_g": 50.0,  # 20 / 40 * 100
            "carbs_g": None,
            "fat_g": None,
            "fiber_g": None,
        }
    ]


async def test_barcode_lookup_nulls_serving_only_data_without_a_gram_serving_size(
    monkeypatch,
) -> None:
    """Serving-only data with no gram-parseable serving_size ("1 cup") can't be
    converted to per-100g at all — must come through null, not silently wrong."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "success",
                "product": {
                    "product_name": "Soup",
                    "serving_size": "1 cup",
                    "nutriments": {"energy-kcal_serving": 120},
                },
            },
        )

    monkeypatch.setattr(service, "_build_client", _client_builder(handler))

    results = await service.search_food_facts(barcode="0000000000002")

    assert results[0]["serving_grams"] is None
    assert results[0]["calories"] is None


async def test_barcode_lookup_falls_back_to_per_100g_and_nulls_missing_macros(
    monkeypatch,
) -> None:
    """No `_serving` nutriments at all (common on OFF): per-100g data alone is fine.

    This product also has no fiber data whatsoever — a real-world gap that must not
    crash normalization; fiber_g should come through as None.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "success",
                "product": {
                    "product_name": "Generic Chocolate Spread",
                    "brands": "Acme",
                    "nutriments": {
                        "energy-kcal_100g": 539,
                        "proteins_100g": 6.3,
                        "carbohydrates_100g": 57.5,
                        "fat_100g": 30.9,
                    },
                },
            },
        )

    monkeypatch.setattr(service, "_build_client", _client_builder(handler))

    results = await service.search_food_facts(barcode="0000000000000")

    assert results == [
        {
            "name": "Generic Chocolate Spread",
            "brand": "Acme",
            "serving_grams": None,
            "calories": 539,
            "protein_g": 6.3,
            "carbs_g": 57.5,
            "fat_g": 30.9,
            "fiber_g": None,
        }
    ]


async def test_barcode_not_found_returns_empty_list_not_an_exception(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "failure", "code": "0", "errors": []})

    monkeypatch.setattr(service, "_build_client", _client_builder(handler))

    assert await service.search_food_facts(barcode="0000000000000") == []


async def test_text_query_normalizes_search_a_licious_hits(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "search.openfoodfacts.org"
        assert request.url.params["q"] == "nutella"
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "product_name": "Nutella",
                        "brands": ["Nutella", "Ferrero"],
                        "nutriments": {
                            "energy-kcal_100g": 539,
                            "proteins_100g": 6.3,
                            "carbohydrates_100g": 57.5,
                            "fat_100g": 30.9,
                            "fiber_100g": 0,
                        },
                    }
                ],
                "count": 1,
            },
        )

    monkeypatch.setattr(service, "_build_client", _client_builder(handler))

    results = await service.search_food_facts(query="nutella")

    assert results == [
        {
            "name": "Nutella",
            "brand": "Nutella, Ferrero",
            "serving_grams": None,
            "calories": 539,
            "protein_g": 6.3,
            "carbs_g": 57.5,
            "fat_g": 30.9,
            "fiber_g": 0,
        }
    ]


async def test_text_query_with_no_hits_returns_empty_list(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hits": [], "count": 0})

    monkeypatch.setattr(service, "_build_client", _client_builder(handler))

    assert await service.search_food_facts(query="asdfqwerty-nonexistent") == []


async def test_neither_query_nor_barcode_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError, match="query or a barcode"):
        await service.search_food_facts()


async def test_barcode_takes_precedence_when_both_given(monkeypatch) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        return httpx.Response(200, json={"status": "success", "product": {"product_name": "X"}})

    monkeypatch.setattr(service, "_build_client", _client_builder(handler))

    await service.search_food_facts(query="nutella", barcode="3017620422003")

    assert calls == ["world.openfoodfacts.org"]


async def test_rest_search_by_barcode_returns_normalized_matches(
    client: AsyncClient, monkeypatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "success",
                "product": {
                    "product_name": "Nutella",
                    "brands": "Nutella, Ferrero",
                    "serving_size": "15 g",
                    "nutriments": {
                        "energy-kcal_100g": 539,
                        "proteins_100g": 6.3,
                        "carbohydrates_100g": 57.5,
                        "fat_100g": 30.9,
                        "fiber_100g": 3.4,
                    },
                },
            },
        )

    monkeypatch.setattr(service, "_build_client", _client_builder(handler))

    resp = await client.get("/api/food-facts/search", params={"barcode": "3017620422003"})

    assert resp.status_code == 200
    assert resp.json() == [
        {
            "name": "Nutella",
            "brand": "Nutella, Ferrero",
            "serving_grams": 15.0,
            "calories": 539,
            "protein_g": 6.3,
            "carbs_g": 57.5,
            "fat_g": 30.9,
            "fiber_g": 3.4,
        }
    ]


async def test_rest_search_requires_query_or_barcode(client: AsyncClient) -> None:
    resp = await client.get("/api/food-facts/search")
    assert resp.status_code == 400
