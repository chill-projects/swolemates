import uuid

from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TmpxItem(Base, TimestampMixin):
    """The disposable template slice. Copy this shape for real features, then delete it.

    `user_id` is the WorkOS `sub` — a provider-issued string, not a UUID, and not a
    foreign key to anything. Every real table gets the same column.
    """

    __tablename__ = "tmpx_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[int] = mapped_column(nullable=False, default=0)

    __table_args__ = (Index("ix_tmpx_items_user_id_created_at", "user_id", "created_at"),)
