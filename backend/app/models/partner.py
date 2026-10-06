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

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
)
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


class Partnership(Base, TimestampMixin):
    """A link between two people, as a row of its own so that membership in it can be
    a per-row fact (see `PartnershipMember`). Carries no columns beyond its id and
    timestamps — it exists to be pointed at."""

    __tablename__ = "partnerships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class PartnershipMember(Base, TimestampMixin):
    """One person's side of a partnership. `UNIQUE(user_id)` is the whole point of this
    table (#40): "a user has at most one partner" is what the code has always believed,
    and as a pair table it was not expressible — `(Alice,Bob)` and `(Alice,Carol)` are
    two individually-valid rows, so no per-row constraint could reject the second, and
    two concurrent redemptions could each pass every Python guard and both commit.

    Here the invariant *is* per-row, so Postgres enforces it at any isolation level and
    a race surfaces as an `IntegrityError` at insert instead of silent corruption that
    permanently 500s every partner endpoint for the affected user.

    A partnership having exactly two members is still not expressible this way — but a
    third member would have to be someone with no partner of their own, and nothing in
    the service inserts outside the pair `redeem_invite` writes.
    """

    __tablename__ = "partnership_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partnership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partnerships.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", name="uq_partnership_members_user_id"),)


class PartnerLink(Base, TimestampMixin):
    """Superseded by `Partnership`/`PartnershipMember` — kept, and still written, only
    for the blue-green overlap: the release before this one reads `partner_links` to
    decide whether someone already has a partner, and would happily create a second
    link during the seconds both versions are serving. Dropped in the follow-up deploy,
    per the never-drop-in-the-same-deploy rule in AGENTS.md.

    `user_id_a < user_id_b` always — callers sort the pair themselves (`min`/`max`)
    before inserting, same as legacy's `least`/`greatest`."""

    __tablename__ = "partner_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id_a: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id_b: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        CheckConstraint("user_id_a < user_id_b", name="ck_partner_links_ordered_pair"),
        UniqueConstraint("user_id_a", "user_id_b", name="uq_partner_links_user_id_a_user_id_b"),
    )
