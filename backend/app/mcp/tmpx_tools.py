from contextlib import asynccontextmanager

from app.auth import mcp_user_sub
from app.db import get_sessionmaker
from app.mcp.server import mcp
from app.services import tmpx as service


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


@mcp.tool
async def whoami() -> str:
    """Report which Swolemates account this connection is authenticated as."""
    return f"Authenticated as {mcp_user_sub()}."


@mcp.tool
async def tmpx_add(name: str, value: int = 0) -> str:
    """Add an item to the caller's TmpX list.

    Args:
        name: What the item is called.
        value: An arbitrary number attached to the item.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        item = await service.add_item(session, user_sub, name=name, value=value)
        return f"Added '{item.name}' (value {item.value})."


@mcp.tool
async def tmpx_list() -> str:
    """List the caller's TmpX items, newest first."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        items = await service.list_items(session, user_sub)

    if not items:
        return "No items yet."
    lines = [f"- {i.name} (value {i.value}, added {i.created_at:%Y-%m-%d %H:%M})" for i in items]
    return f"{len(items)} item(s):\n" + "\n".join(lines)
