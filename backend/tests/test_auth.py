"""Guards on the local-dev auth bypass.

DEV_USER_SUB exists so the dev loop doesn't need an OAuth round trip per request. That
convenience is exactly the kind of thing that ships to production by accident, so its
inertness outside local dev is a test, not a comment.
"""

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.requests import Request

from app.auth import require_principal
from app.config import Settings


def _request(headers: dict[str, str] | None = None) -> Request:
    raw = Headers(headers or {}).raw
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw})


async def test_dev_bypass_applies_in_local() -> None:
    settings = Settings(environment="local", dev_user_sub="dev_abc")
    principal = await require_principal(_request(), settings)
    assert principal.sub == "dev_abc"


@pytest.mark.parametrize("environment", ["test", "production"])
async def test_dev_bypass_is_inert_outside_local(environment: str) -> None:
    settings = Settings(
        environment=environment,
        dev_user_sub="dev_abc",
        authkit_domain="https://example.authkit.app",
        workos_client_id="client_123",
        public_url="https://example.up.railway.app",
    )
    with pytest.raises(HTTPException) as exc:
        await require_principal(_request(), settings)
    assert exc.value.status_code == 401


async def test_production_config_rejects_missing_authkit() -> None:
    with pytest.raises(ValueError, match="authkit_domain"):
        Settings(environment="production", authkit_domain="", workos_client_id="")


async def test_production_config_rejects_the_localhost_public_url() -> None:
    """public_url is the OAuth token audience.

    Its default is a localhost URL, so an unset value in production isn't empty — it's
    wrong. Every token would then fail audience validation and the symptom would be a
    login loop, not a boot failure. Fail loudly at startup instead.
    """
    with pytest.raises(ValueError, match="public_url"):
        Settings(
            environment="production",
            authkit_domain="https://example.authkit.app",
            workos_client_id="client_123",
        )


@pytest.mark.parametrize(
    "header",
    ["token abc", "Bearer", "Bearer "],
)
async def test_malformed_authorization_header_is_rejected(header: str) -> None:
    settings = Settings(environment="local", dev_user_sub="dev_abc")
    with pytest.raises(HTTPException) as exc:
        await require_principal(_request({"Authorization": header}), settings)
    assert exc.value.status_code == 401
