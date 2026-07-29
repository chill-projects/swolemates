from fastapi import APIRouter

from app.api import tmpx
from app.deps import CurrentUser

api_router = APIRouter()
api_router.include_router(tmpx.router)


@api_router.get("/whoami", tags=["auth"], operation_id="whoami")
async def whoami(user_sub: CurrentUser) -> dict[str, str]:
    """The auth spike's REST half. If this returns your WorkOS sub, the browser flow works."""
    return {"user_sub": user_sub}
