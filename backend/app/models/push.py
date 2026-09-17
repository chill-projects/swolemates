"""Web Push subscriptions.

A row per *device*, not per user: someone installs the PWA on their phone and later
opens it on a laptop, and each browser mints its own subscription. Storing one per user
would silently stop notifying the phone the moment the laptop subscribed — the kind of
failure nobody reports, because nothing appears broken.

The three fields after `user_id` are exactly what the Push API hands back
(`PushSubscription.toJSON()`): where to POST, and the two keys the payload is encrypted
against. We never decrypt anything; they're carried straight through to `pywebpush`.
"""

import uuid

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PushSubscription(Base, TimestampMixin):
    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Push-service URLs have no documented length bound, so Text rather than a guess.
    # Unique because re-subscribing the same browser returns the same endpoint, and a
    # re-subscribe must update the row rather than accumulate duplicates that would each
    # deliver their own copy of the same notification.
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),)
