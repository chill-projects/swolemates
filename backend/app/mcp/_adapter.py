"""Shared MCP tool adapter (architecture review, 2026-08-14): a database session per
call, plus safe-by-default error handling.

Every `@mcp.tool` function should be `@catches_service_errors`, applied directly below
`@mcp.tool` so it wraps the raw tool body before FastMCP sees it:

    @mcp.tool
    @catches_service_errors
    async def some_tool(...) -> str:
        ...

This is deliberately just a decorator around the tool body, not a session-injecting one
(no FastMCP `Depends()`) — `tool_session()` stays an explicit `async with` inside each
tool, same as before, just no longer copy-pasted into every `*_tools.py` module.
"""

import functools
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from app.db import get_sessionmaker
from app.services.errors import NotFoundError


@asynccontextmanager
async def tool_session():
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def catches_service_errors[F: Callable[..., Awaitable[Any]]](fn: F) -> F:
    """A service-layer ValueError/NotFoundError becomes the tool's return value
    (`str(exc)`) instead of an uncaught exception reaching the model — matching this
    app's established convention (search_food_facts, set_goals) that a validation
    failure is a normal, friendly reply, not a broken tool call.

    Applies uniformly regardless of a tool's declared return type: FastMCP doesn't
    enforce a tool's return value against its output schema, and every host already
    tolerates a plain-text fallback (the nutrition-day component's `extractPayload`
    shows "Waiting for data…" rather than crashing when structuredContent is absent).
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except (ValueError, NotFoundError) as exc:
            return str(exc)

    return wrapper  # type: ignore[return-value]
