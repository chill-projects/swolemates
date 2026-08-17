import inspect

import pytest

from app.mcp._adapter import catches_service_errors
from app.services.errors import NotFoundError


async def test_catches_service_errors_returns_value_error_text() -> None:
    @catches_service_errors
    async def fails() -> str:
        raise ValueError("bad input")

    assert await fails() == "bad input"


async def test_catches_service_errors_returns_not_found_error_text() -> None:
    @catches_service_errors
    async def fails() -> str:
        raise NotFoundError("no such thing")

    assert await fails() == "no such thing"


async def test_catches_service_errors_does_not_swallow_other_exceptions() -> None:
    """Only ValueError/NotFoundError are user-facing failures — anything else (a
    typo, a DB error) should stay loud, not be silently reported as if it were a
    friendly validation message (#3/#4 architecture review, resolved)."""

    @catches_service_errors
    async def fails() -> str:
        raise RuntimeError("a real bug")

    with pytest.raises(RuntimeError, match="a real bug"):
        await fails()


async def test_catches_service_errors_passes_through_normal_returns() -> None:
    @catches_service_errors
    async def succeeds(x: int, y: int = 1) -> int:
        return x + y

    assert await succeeds(2, y=3) == 5


def test_catches_service_errors_preserves_signature_name_and_docstring() -> None:
    async def example(log_id: str, name: str | None = None) -> str:
        """Example docstring."""
        return log_id

    wrapped = catches_service_errors(example)

    assert wrapped.__name__ == "example"
    assert wrapped.__doc__ == "Example docstring."
    assert inspect.signature(wrapped) == inspect.signature(example)
