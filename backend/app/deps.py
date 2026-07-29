"""Shared FastAPI dependency aliases.

`Annotated[...]` rather than `= Depends(...)` defaults: same behaviour, but the signature
stays a real type annotation, so linters and type checkers read it correctly.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.config import Settings, get_settings
from app.db import get_session

CurrentUser = Annotated[str, Depends(require_user)]
DbSession = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
