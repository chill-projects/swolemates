"""Partner v1 (#5/#12, resolved) — one accountability partner per user, linked via a
short-lived invite code. Ported from `docs/legacy/schema/0002_partner_links.sql` onto
WorkOS identities: `user_id_a`/`user_id_b` are plain `String(255)` subs (the same
no-FK convention used everywhere else in this app) rather than UUID profile FKs, and
the ordered-pair invariant is enforced the same way (`least`/`greatest` at insert
time, backed by a `CHECK` here) since Python string comparison sorts the same way SQL
`<`/`>` did on legacy's UUID text form.

Names (for the invite preview and the partner summary) come from `UserProfile.display_name` —
see that model's docstring for why a cache exists there at all.
"""

import enum
import uuid

from sqlalchemy import CheckConstraint, DateTime, Enum, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class InviteStatus(enum.StrEnum):
    pending = "pending"
    redeemed = "redeemed"
    expired = "expired"


class PartnerInvite(Base, TimestampMixin):
    __tablename__ = "partner_invites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inviter_id: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    status: Mapped[InviteStatus] = mapped_column(
        Enum(InviteStatus, name="invite_status"), nullable=False, default=InviteStatus.pending
    )
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_by: Mapped[str | None] = mapped_column(String(255))
    redeemed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class PartnerLink(Base, TimestampMixin):
    """`user_id_a < user_id_b` always — callers sort the pair themselves
    (`min`/`max`) before inserting, same as legacy's `least`/`greatest`."""

    __tablename__ = "partner_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id_a: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id_b: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        CheckConstraint("user_id_a < user_id_b", name="ck_partner_links_ordered_pair"),
        UniqueConstraint("user_id_a", "user_id_b", name="uq_partner_links_user_id_a_user_id_b"),
    )
