"""Every model must be imported here — Alembic autogenerate only sees registered tables."""

from app.models.base import Base, TimestampMixin
from app.models.tmpx import TmpxItem

__all__ = ["Base", "TimestampMixin", "TmpxItem"]
