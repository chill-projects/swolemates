import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TrackableType(Base):
    """The trackable registry (#4, resolved). A new trackable is a seed row, never an
    `ALTER TABLE` — the 5 starter rows (calories/protein_g/carbs_g/fat_g/fiber_g) are
    seeded inside the migration that creates this table, since this app has no other
    pre-deploy seeding step yet (`docs/design.md` §5: only `alembic upgrade head`).
    """

    __tablename__ = "trackable_types"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    goal_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Log(Base, TimestampMixin):
    """One logged event — a meal, a glass of water, a supplement dose. Header row; the
    actual metrics are in `LogValue` (one header, many values — a photo estimate writes
    5 values under one Log; a water log writes 1). `user_id` is the WorkOS `sub`,
    `String(255)`, no FK, filtered in the service layer — the app-wide convention.
    """

    __tablename__ = "logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    logged_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # manual|search|photo|template
    source_ref: Mapped[str | None] = mapped_column(String(255))
    photo_storage_path: Mapped[str | None] = mapped_column(String(500))
    name: Mapped[str | None] = mapped_column(String(200))
    serving_description: Mapped[str | None] = mapped_column(String(200))
    meal_type: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[dict | None] = mapped_column(JSONB)
    raw_ai_response: Mapped[dict | None] = mapped_column(JSONB)
    edited_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (Index("ix_logs_user_id_logged_at", "user_id", "logged_at"),)


class LogValue(Base):
    __tablename__ = "log_values"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("logs.id", ondelete="CASCADE"), nullable=False
    )
    trackable_key: Mapped[str] = mapped_column(ForeignKey("trackable_types.key"), nullable=False)
    value: Mapped[object] = mapped_column(Numeric, nullable=False)

    __table_args__ = (Index("ix_log_values_log_id", "log_id"),)


class Goal(Base, TimestampMixin):
    """One row per (user, trackable) — `period` is always `daily` for v1. `set_goals`
    upserts against the unique constraint below. `is_streak_target`: at most one true
    per user, enforced in the service layer (not a DB constraint — #6, resolved).
    """

    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    trackable_key: Mapped[str] = mapped_column(ForeignKey("trackable_types.key"), nullable=False)
    target_value: Mapped[object] = mapped_column(Numeric, nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False, default="daily")
    is_streak_target: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("user_id", "trackable_key", name="uq_goals_user_id_trackable_key"),
    )
