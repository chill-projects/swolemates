import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastmcp.utilities.lifespan import combine_lifespans
from sqlalchemy import text

from app.api import api_router
from app.config import get_settings
from app.db import dispose_engine
from app.deps import DbSession
from app.mcp.server import mcp

logging.basicConfig(level=logging.INFO)

settings = get_settings()

# The SPA is built into the image at /app/static. Absent in local dev, where Vite serves it.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def app_lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


# Stateless Streamable HTTP: the 2026-07-28 spec dropped sessions, and stateless is what
# lets Railway load-balance across replicas without sticky routing.
# FastMCP's ASGI app carries its own lifespan (session manager setup); it has to run
# alongside ours, not instead of it.
mcp_app = mcp.http_app(path="/", stateless_http=True)

app = FastAPI(
    title="Swolemates",
    version="0.1.0",
    lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan),
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness only — deliberately does not touch the database.

    Railway gates its blue-green cutover on this. If it depended on Postgres, a brief
    database blip would block deploys of code that has nothing to do with the database.
    Use /health/ready for the dependency check.
    """
    return {"status": "ok", "environment": settings.environment}


@app.get("/health/ready", tags=["ops"])
async def ready(session: DbSession) -> JSONResponse:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - reported, not raised, so probes see a body
        return JSONResponse(status_code=503, content={"status": "degraded", "database": str(exc)})
    return JSONResponse({"status": "ok", "database": "ok"})


app.include_router(api_router, prefix="/api")
app.mount("/mcp", mcp_app)

# --- SPA ---------------------------------------------------------------------------
# Mounted last so /api, /mcp and /health always win. Unknown paths fall through to
# index.html because the SPA owns client-side routing.
if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
