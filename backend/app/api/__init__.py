from fastapi import APIRouter
from pydantic import BaseModel

from app.api import food_facts, nutrition, profile, tmpx
from app.deps import AppSettings, CurrentPrincipal

api_router = APIRouter()
api_router.include_router(tmpx.router)
api_router.include_router(profile.router)
api_router.include_router(nutrition.router)
api_router.include_router(food_facts.router)


class WhoamiOut(BaseModel):
    user_sub: str
    email: str | None
    display_name: str | None


class AuthConfigOut(BaseModel):
    configured: bool
    authkit_domain: str
    client_id: str
    redirect_uri: str
    # RFC 8707 resource indicator the SPA must request; becomes the token's `aud`,
    # which the backend validates. Must be listed as a Resource Indicator in WorkOS.
    resource: str
    environment: str


@api_router.get("/whoami", tags=["auth"], operation_id="whoami")
async def whoami(principal: CurrentPrincipal) -> WhoamiOut:
    """The auth spike's REST half. If this returns your WorkOS sub, the browser flow works.

    email/first_name/last_name come from the environment's JWT template — they're custom
    claims, not defaults, so a missing email means the template got dropped in WorkOS.
    """
    claims = principal.claims
    name = " ".join(p for p in (claims.get("first_name"), claims.get("last_name")) if p)
    return WhoamiOut(
        user_sub=principal.sub,
        email=claims.get("email"),
        display_name=name or None,
    )


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
        resource=settings.public_url.rstrip("/"),
        # Lets the SPA explain itself when auth isn't wired up yet, rather than
        # rendering a bare error the user can do nothing about.
        environment=settings.environment,
    )
