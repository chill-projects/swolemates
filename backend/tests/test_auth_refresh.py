"""Browser session endpoints — `/api/auth/session`, `/api/auth/refresh`, `/api/auth/logout`.

The refresh token is an httpOnly cookie now. `_build_client` is swapped for a
`MockTransport` so no real call reaches WorkOS, matching test_food_facts.py.
"""

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.auth import REFRESH_COOKIE
from app.config import Settings, get_settings
from app.services import auth as auth_service

TEST_SUB = "user_test_123"


def _client_builder(handler):
    def build_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=10.0)

    return build_client


def _with_cookie(client: AsyncClient, value: str) -> AsyncClient:
    """httpx deprecated per-request `cookies=`; set it on the client instead."""
    client.cookies.set(REFRESH_COOKIE, value)
    return client


@pytest.fixture
async def anon_client() -> AsyncClient:
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: Settings(
        workos_client_id="client_123", workos_client_secret="sk_test_abc"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def authed_client(anon_client: AsyncClient) -> AsyncClient:
    from app.auth import require_user
    from app.main import app

    app.dependency_overrides[require_user] = lambda: TEST_SUB
    yield anon_client
    # anon_client's fixture clears all overrides on teardown.


async def test_create_session_sets_httponly_refresh_cookie(authed_client: AsyncClient) -> None:
    res = await authed_client.post("/api/auth/session", json={"refresh_token": "rt_1"})

    assert res.status_code == 204
    set_cookie = res.headers["set-cookie"]
    assert f"{REFRESH_COOKIE}=rt_1" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/api/auth" in set_cookie
    assert "SameSite=lax" in set_cookie


async def test_create_session_requires_a_valid_access_token(anon_client: AsyncClient) -> None:
    res = await anon_client.post("/api/auth/session", json={"refresh_token": "rt_1"})
    assert res.status_code == 401


async def test_refresh_reads_cookie_rotates_it_and_returns_new_access_token(
    monkeypatch, anon_client: AsyncClient
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.read())["refresh_token"] == "rt_old"
        return httpx.Response(200, json={"access_token": "at_new", "refresh_token": "rt_new"})

    monkeypatch.setattr(auth_service, "_build_client", _client_builder(handler))

    res = await _with_cookie(anon_client, "rt_old").post("/api/auth/refresh")

    assert res.status_code == 200
    assert res.json() == {"access_token": "at_new"}
    assert f"{REFRESH_COOKIE}=rt_new" in res.headers["set-cookie"]


async def test_refresh_without_a_cookie_is_401(anon_client: AsyncClient) -> None:
    res = await anon_client.post("/api/auth/refresh")
    assert res.status_code == 401


async def test_refresh_rejected_by_workos_is_401_and_clears_the_cookie(
    monkeypatch, anon_client: AsyncClient
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    monkeypatch.setattr(auth_service, "_build_client", _client_builder(handler))

    res = await _with_cookie(anon_client, "rt_spent").post("/api/auth/refresh")

    assert res.status_code == 401
    # cleared → Max-Age=0 / expiry in the past
    set_cookie = res.headers["set-cookie"]
    assert f'{REFRESH_COOKIE}=""' in set_cookie or f"{REFRESH_COOKIE}=;" in set_cookie


async def test_refresh_upstream_error_is_502_and_keeps_the_cookie(
    monkeypatch, anon_client: AsyncClient
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream is down")

    monkeypatch.setattr(auth_service, "_build_client", _client_builder(handler))

    res = await _with_cookie(anon_client, "rt_ok").post("/api/auth/refresh")

    assert res.status_code == 502
    assert "set-cookie" not in res.headers  # session left intact


async def test_refresh_network_failure_is_502(monkeypatch, anon_client: AsyncClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(auth_service, "_build_client", _client_builder(handler))

    res = await _with_cookie(anon_client, "rt_ok").post("/api/auth/refresh")
    assert res.status_code == 502


async def test_refresh_without_configured_secret_is_500_not_401() -> None:
    """A config slip must not read to the client as 'signed out' — otherwise it logs
    out every user at once."""
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: Settings(workos_client_id="client_123")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        c.cookies.set(REFRESH_COOKIE, "whatever")
        res = await c.post("/api/auth/refresh")
    app.dependency_overrides.clear()

    assert res.status_code == 500


async def test_logout_clears_the_cookie(anon_client: AsyncClient) -> None:
    res = await anon_client.post("/api/auth/logout")
    assert res.status_code == 204
    assert REFRESH_COOKIE in res.headers["set-cookie"]


async def test_refresh_session_classifies_workos_errors(monkeypatch) -> None:
    """Unit-level: the service raises the right typed error per WorkOS response."""
    settings = Settings(workos_client_id="c", workos_client_secret="s")

    monkeypatch.setattr(
        auth_service,
        "_build_client",
        _client_builder(lambda _req: httpx.Response(400, json={"error": "invalid_grant"})),
    )
    with pytest.raises(auth_service.RefreshRejected):
        await auth_service.refresh_session(settings, "rt")

    monkeypatch.setattr(
        auth_service,
        "_build_client",
        _client_builder(lambda _req: httpx.Response(500, text="boom")),
    )
    with pytest.raises(auth_service.RefreshUpstreamError):
        await auth_service.refresh_session(settings, "rt")

    with pytest.raises(auth_service.RefreshConfigError):
        await auth_service.refresh_session(Settings(workos_client_id="c"), "rt")
