from fastapi import APIRouter
from pydantic import BaseModel

from app.api import tmpx
from app.deps import AppSettings, CurrentUser

api_router = APIRouter()
api_router.include_router(tmpx.router)


class WhoamiOut(BaseModel):
    user_sub: str


class AuthConfigOut(BaseModel):
    configured: bool
    authkit_domain: str
    client_id: str
    redirect_uri: str
    environment: str


@api_router.get("/whoami", tags=["auth"], operation_id="whoami")
async def whoami(user_sub: CurrentUser) -> WhoamiOut:
    """The auth spike's REST half. If this returns your WorkOS sub, the browser flow works."""
    return WhoamiOut(user_sub=user_sub)


@api_router.get("/auth/config", tags=["auth"], operation_id="authConfig")
async def auth_config(settings: AppSettings) -> AuthConfigOut:
    """Public: what the SPA needs to start an AuthKit login.

    Unauthenticated by design — the browser has to read this *before* it has a token.
    It exposes only the client id and issuer, both of which are public values in an
    OAuth public-client flow. No secret is involved; AuthKit is PKCE-only here.
    """
    return AuthConfigOut(
        configured=bool(settings.authkit_domain and settings.workos_client_id),
        authkit_domain=settings.authkit_domain,
        client_id=settings.workos_client_id,
        redirect_uri=f"{settings.public_url.rstrip('/')}/callback",
        # Lets the SPA explain itself when auth isn't wired up yet, rather than
        # rendering a bare error the user can do nothing about.
        environment=settings.environment,
    )
