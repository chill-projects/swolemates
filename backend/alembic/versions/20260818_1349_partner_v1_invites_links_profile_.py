"""partner v1: invites, links, profile display_name

Revision ID: d0563dd9088f
Revises: 4f2e6a7c9d31
Create Date: 2026-08-18 13:49:36.210316

Blue-green note: additive-only, no drop/rename in the same deploy.

#5/#12, resolved. Ported from docs/legacy/schema/0002_partner_links.sql onto WorkOS
identities — `user_id_a`/`user_id_b` are plain subs, ordered-pair invariant enforced
the same way (least/greatest at insert time, backed by the CHECK here).
`user_profiles.display_name` is a new cache (see UserProfile's docstring): a linked
partner's name has no other persistence path, since WorkOS claims are per-request JWT
contents, never stored. Autogenerate also picked up an unrelated pre-existing drift on
`logs.confidence`/`raw_ai_response` (JSON vs. the model's JSONB) — left untouched here,
out of scope for this migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "d0563dd9088f"
down_revision: str | None = "4f2e6a7c9d31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No manual .create() here: op.create_table() below auto-creates the inline
    # enum type; calling both double-creates it.
    op.create_table(
        "partner_invites",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("inviter_id", sa.String(255), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "redeemed", "expired", name="invite_status"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_by", sa.String(255), nullable=True),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("code", name="uq_partner_invites_code"),
    )

    op.create_table(
        "partner_links",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id_a", sa.String(255), nullable=False),
        sa.Column("user_id_b", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("user_id_a < user_id_b", name="ck_partner_links_ordered_pair"),
        sa.UniqueConstraint("user_id_a", "user_id_b", name="uq_partner_links_user_id_a_user_id_b"),
    )

    op.add_column("user_profiles", sa.Column("display_name", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profiles", "display_name")
    op.drop_table("partner_links")
    op.drop_table("partner_invites")
    invite_status = sa.Enum(name="invite_status")
    invite_status.drop(op.get_bind(), checkfirst=True)
