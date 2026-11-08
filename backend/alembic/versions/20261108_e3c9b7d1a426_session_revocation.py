"""users.sessions_revoked_at: end access tokens immediately on password reset.

Revision ID: e3c9b7d1a426
Revises: d2a8e6f0b137
Create Date: 2026-11-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e3c9b7d1a426"
down_revision = "d2a8e6f0b137"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("sessions_revoked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "sessions_revoked_at")
