"""POST /api/auth/refresh — the server-side leg of the refresh-token exchange.

Unauthenticated (the caller doesn't have a live access token yet), so these tests don't
need the `client` fixture's auth overrides — only its ASGI transport. `_build_client` is
swapped for a MockTransport so no real call reaches WorkOS, matching test_food_facts.py.
"""

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings, get_settings
from app.services import auth as auth_service


def _client_builder(handler):
    def build_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=10.0)

    return build_client


@pytest.fixture
async def anon_client(monkeypatch) -> AsyncClient:
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: Settings(
        workos_client_id="client_123", workos_client_secret="sk_test_abc"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_refresh_exchanges_and_rotates_token(monkeypatch, anon_client: AsyncClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.workos.com/user_management/authenticate"
        body = request.read()
        import json

        payload = json.loads(body)
        assert payload == {
            "client_id": "client_123",
            "client_secret": "sk_test_abc",
            "grant_type": "refresh_token",
            "refresh_token": "old_refresh",
        }
        return httpx.Response(
            200, json={"access_token": "new_access", "refresh_token": "new_refresh"}
        )

    monkeypatch.setattr(auth_service, "_build_client", _client_builder(handler))

    res = await anon_client.post("/api/auth/refresh", json={"refresh_token": "old_refresh"})

    assert res.status_code == 200
    assert res.json() == {"access_token": "new_access", "refresh_token": "new_refresh"}


async def test_refresh_rejected_by_workos_is_a_401(monkeypatch, anon_client: AsyncClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    monkeypatch.setattr(auth_service, "_build_client", _client_builder(handler))

    res = await anon_client.post("/api/auth/refresh", json={"refresh_token": "stale"})

    assert res.status_code == 401


async def test_refresh_without_configured_secret_is_a_401() -> None:
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: Settings(workos_client_id="client_123")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        res = await c.post("/api/auth/refresh", json={"refresh_token": "whatever"})
    app.dependency_overrides.clear()

    assert res.status_code == 401
