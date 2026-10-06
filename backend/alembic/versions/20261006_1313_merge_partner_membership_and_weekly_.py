"""merge partner membership and weekly reminder heads

Revision ID: 937641e786e2
Revises: c7a13f5e6d84, af364567dc8e
Create Date: 2026-10-06 13:13:17.200576

#41 and #44 were each written against a1c4e7f09b22 and merged independently, leaving
two heads — which `alembic upgrade head` (pre-deploy and the test fixture) refuses.
This joins them; it changes no schema. A merge revision rather than re-pointing
af364567dc8e, so a database already at either head still upgrades cleanly.
"""

from collections.abc import Sequence

revision: str = "937641e786e2"
down_revision: str | tuple[str, ...] | None = ("c7a13f5e6d84", "af364567dc8e")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
