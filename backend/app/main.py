import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastmcp.utilities.lifespan import combine_lifespans
from sqlalchemy import text

from app.api import api_router
from app.config import get_settings
from app.db import dispose_engine
from app.deps import DbSession
from app.mcp.server import mcp

settings = get_settings()

logging.basicConfig(level=settings.log_level)

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

# docs_url/redoc_url off, then re-served below: FastAPI's built-in pages hardcode
# fastapi.tiangolo.com's favicon, so /docs and /redoc sat on our own origin wearing
# someone else's mark.
app = FastAPI(
    title="Swolemates",
    version="0.1.0",
    lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan),
    docs_url=None,
    redoc_url=None,
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


@app.get("/docs", include_in_schema=False)
async def swagger_ui() -> HTMLResponse:
    """The stock page with our favicon. Registered before the SPA catch-all, so it
    still wins over client-side routing the way FastAPI's own /docs did."""
    return get_swagger_ui_html(
        openapi_url=str(app.openapi_url),
        title=f"{app.title} API",
        swagger_favicon_url="/favicon.ico",
    )


@app.get("/redoc", include_in_schema=False)
async def redoc() -> HTMLResponse:
    return get_redoc_html(
        openapi_url=str(app.openapi_url),
        title=f"{app.title} API",
        redoc_favicon_url="/favicon.ico",
    )


app.include_router(api_router, prefix="/api")
app.mount("/mcp", mcp_app)


class NormalizeMcpPath:
    """Rewrite the exact path /mcp to /mcp/ before routing.

    Starlette's Mount only matches the prefix-with-slash form, so bare /mcp fell
    through to the SPA catch-all (GET served index.html, POST got 405 — which claude.ai
    reports as "no MCP server found"). A 307 redirect isn't safe here: MCP clients use
    httpx, which doesn't follow redirects by default. Pure ASGI rewrite, so streaming
    responses pass through untouched.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == "/mcp":
            scope = dict(scope)
            scope["path"] = "/mcp/"
            scope["raw_path"] = b"/mcp/"
        await self.inner(scope, receive, send)


app.add_middleware(NormalizeMcpPath)


@app.get("/.well-known/{suffix:path}", include_in_schema=False)
async def well_known(suffix: str, request: Request) -> Response:
    """Forward root /.well-known/* into the mounted MCP app.

    RFC 9728: an MCP client that gets a 401 from /mcp fetches OAuth resource metadata
    at the ORIGIN ROOT (/.well-known/oauth-protected-resource), but FastMCP serves it
    inside its mount (/mcp/.well-known/...). Without this forward the SPA catch-all
    swallows the path and returns index.html, and the claude.ai connector flow dies at
    its very first step. Verified against the live 401's WWW-Authenticate header.
    """
    transport = httpx.ASGITransport(app=mcp_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://mcp") as client:
        upstream = await client.get(f"/.well-known/{suffix}", params=request.query_params)
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )


# --- SPA ---------------------------------------------------------------------------
# Mounted last so /api, /mcp and /health always win. Unknown paths fall through to
# index.html because the SPA owns client-side routing.

# ...except these. Every one is fetched as a file by something that is not a browser
# navigating the app: the tab icon, iOS's home-screen icon, the install manifest, the
# service worker, and — since MCP serverInfo.icons point here — Claude rendering the
# connector's mark. Handing any of them index.html at 200 is worse than a 404: the
# fetcher sees success, silently shows a fallback icon (Railway's, on a
# *.up.railway.app host) or silently declines to register the worker, and nothing in
# the logs says the file went missing from the image.
ROOT_ASSETS = frozenset(
    {
        "favicon.ico",
        "apple-touch-icon.png",
        "icon-192.png",
        "icon-512.png",
        "icon-maskable-512.png",
        "manifest.webmanifest",
        "sw.js",
        "registerSW.js",
    }
)

if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        candidate = STATIC_DIR / full_path
        if full_path in ROOT_ASSETS and not candidate.is_file():
            raise HTTPException(status_code=404, detail=f"{full_path} is missing from the build")
        if full_path and candidate.is_file():
            headers = None
            if full_path.startswith("mcp-apps/"):
                # These bundles have no content hash in their filename and change
                # underneath a stable URL as slices land — a browser (or intermediate
                # proxy) caching the old bytes silently shows a stale component.
                headers = {"Cache-Control": "no-store"}
            return FileResponse(candidate, headers=headers)
        return FileResponse(STATIC_DIR / "index.html")
