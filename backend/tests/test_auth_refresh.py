"""Browser session endpoints — `/api/auth/session`, `/api/auth/refresh`, `/api/auth/logout`.

The refresh token is an httpOnly cookie now. `_build_client` is swapped for a
`MockTransport` so no real call reaches WorkOS, matching test_food_facts.py.

Refresh goes to the AuthKit domain's `/oauth2/token` as the same PKCE public client
that logged in — form-encoded, no `client_secret`. It used to post to
`/user_management/authenticate`, which authenticates a different kind of application
entirely and answered `invalid_client` every time. The endpoint and the body shape
are pinned by `test_refresh_posts_a_public_client_form_grant_to_authkit`.
"""

from urllib.parse import parse_qs

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.auth import REFRESH_COOKIE
from app.config import Settings, get_settings
from app.services import auth as auth_service

TEST_SUB = "user_test_123"
AUTHKIT_DOMAIN = "https://test-domain.authkit.app"
CLIENT_ID = "client_123"


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
        workos_client_id=CLIENT_ID, authkit_domain=AUTHKIT_DOMAIN
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
        assert parse_qs(request.read().decode())["refresh_token"] == ["rt_old"]
        return httpx.Response(200, json={"access_token": "at_new", "refresh_token": "rt_new"})

    monkeypatch.setattr(auth_service, "_build_client", _client_builder(handler))

    res = await _with_cookie(anon_client, "rt_old").post("/api/auth/refresh")

    assert res.status_code == 200
    assert res.json() == {"access_token": "at_new"}
    assert f"{REFRESH_COOKIE}=rt_new" in res.headers["set-cookie"]


async def test_refresh_posts_a_public_client_form_grant_to_authkit(
    monkeypatch, anon_client: AsyncClient
) -> None:
    """The regression that logged everyone out every few minutes: refresh must hit the
    AuthKit domain's own token endpoint as the PKCE public client. Posting to
    `/user_management/authenticate` — or sending a `client_secret` — is a different
    application with a different credential system, and always fails `invalid_client`."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["content_type"] = request.headers.get("content-type", "")
        seen["body"] = parse_qs(request.read().decode())
        return httpx.Response(200, json={"access_token": "at_new", "refresh_token": "rt_new"})

    monkeypatch.setattr(auth_service, "_build_client", _client_builder(handler))

    res = await _with_cookie(anon_client, "rt_old").post("/api/auth/refresh")
    assert res.status_code == 200

    assert seen["url"] == f"{AUTHKIT_DOMAIN}/oauth2/token"
    assert "application/x-www-form-urlencoded" in seen["content_type"]  # type: ignore[operator]
    body = seen["body"]
    assert body == {
        "grant_type": ["refresh_token"],
        "client_id": [CLIENT_ID],
        "refresh_token": ["rt_old"],
    }
    # `resource` is bound at the authorize leg; repeating it here returns invalid_target.
    assert "client_secret" not in body
    assert "resource" not in body


async def test_refresh_without_a_cookie_is_401_coded_no_session(
    anon_client: AsyncClient,
) -> None:
    """401 with `no_session` — nothing was ever presented, so no live credential died.
    The client shows sign-in but must not tear down state it may still be able to use."""
    res = await anon_client.post("/api/auth/refresh")
    assert res.status_code == 401
    assert res.json()["code"] == "no_session"


async def test_refresh_rejected_by_workos_is_401_and_clears_the_cookie(
    monkeypatch, anon_client: AsyncClient
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    monkeypatch.setattr(auth_service, "_build_client", _client_builder(handler))

    res = await _with_cookie(anon_client, "rt_spent").post("/api/auth/refresh")

    assert res.status_code == 401
    # ...and `session_expired`, not `no_session`: this is the one that signs the user out.
    assert res.json()["code"] == "session_expired"
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


async def test_refresh_without_configured_authkit_domain_is_500_not_401() -> None:
    """A config slip must not read to the client as 'signed out' — otherwise it logs
    out every user at once. Refresh needs a client id and an AuthKit domain to build
    the token URL; neither is a secret."""
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: Settings(workos_client_id=CLIENT_ID)
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
    settings = Settings(workos_client_id=CLIENT_ID, authkit_domain=AUTHKIT_DOMAIN)

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
        await auth_service.refresh_session(Settings(workos_client_id=CLIENT_ID), "rt")
    with pytest.raises(auth_service.RefreshConfigError):
        await auth_service.refresh_session(Settings(authkit_domain=AUTHKIT_DOMAIN), "rt")
