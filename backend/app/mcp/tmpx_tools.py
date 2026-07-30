from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastmcp.apps import AppConfig

from app.auth import mcp_user_sub
from app.db import get_sessionmaker
from app.mcp.server import mcp
from app.services import tmpx as service

TMPX_UI_URI = "ui://swolemates/tmpx.html"

# Built by `make apps` (frontend/src/mcp-apps/tmpx → vite single-file bundle). The same
# file renders in Claude (via the ui:// resource below) and in the SPA (fetched over
# HTTP and hosted in an iframe by AppRenderer).
TMPX_UI_BUNDLE = Path(__file__).resolve().parent.parent.parent / "static" / "mcp-apps" / "tmpx.html"


@asynccontextmanager
async def tool_session():
    """MCP tools aren't FastAPI requests, so they manage their own session lifecycle."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _items_payload(session, user_sub: str) -> dict:
    """The one payload shape every TmpX tool returns.

    `items` feeds the UI component; `summary` is the plain-text story for hosts that
    don't render apps. Tools returning the full list after every mutation is what lets
    the component re-render from any tool result without extra round trips.
    """
    items = await service.list_items(session, user_sub)
    return {
        "items": [
            {
                "id": str(i.id),
                "name": i.name,
                "value": i.value,
                "created_at": i.created_at.isoformat(),
            }
            for i in items
        ],
        "summary": (
            "No items yet."
            if not items
            else f"{len(items)} item(s): " + ", ".join(f"{i.name} ({i.value})" for i in items)
        ),
    }


@mcp.tool
async def whoami() -> str:
    """Report which Swolemates account this connection is authenticated as."""
    return f"Authenticated as {mcp_user_sub()}."


@mcp.tool(app=AppConfig(resource_uri=TMPX_UI_URI))
async def tmpx_list() -> dict:
    """Show the caller's TmpX items in an interactive list."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        return await _items_payload(session, user_sub)


@mcp.tool(app=AppConfig(resource_uri=TMPX_UI_URI, visibility=["model", "app"]))
async def tmpx_add(name: str, value: int = 0) -> dict:
    """Add an item to the caller's TmpX list.

    Args:
        name: What the item is called.
        value: An arbitrary number attached to the item.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        await service.add_item(session, user_sub, name=name, value=value)
        return await _items_payload(session, user_sub)


@mcp.tool(app=AppConfig(resource_uri=TMPX_UI_URI, visibility=["model", "app"]))
async def tmpx_delete(item_id: str) -> dict:
    """Delete one of the caller's TmpX items by id."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        try:
            await service.delete_item(session, user_sub, UUID(item_id))
        except (service.NotFoundError, ValueError):
            pass  # deleting something already gone is not an error worth surfacing
        return await _items_payload(session, user_sub)


@mcp.resource(TMPX_UI_URI)
def tmpx_ui() -> str:
    """The TmpX component — one bundle rendered by Claude and the SPA alike."""
    if TMPX_UI_BUNDLE.is_file():
        return TMPX_UI_BUNDLE.read_text()
    return (
        "<html><body style='font-family:system-ui;padding:1rem'>"
        "<p>The TmpX component bundle isn't built. Run <code>make apps</code>.</p>"
        "</body></html>"
    )
