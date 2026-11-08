"""media_assets.blob: store uploads in the database (no persistent disk on free hosts).

Revision ID: d2a8e6f0b137
Revises: c7a1e4b90f22
Create Date: 2026-11-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d2a8e6f0b137"
down_revision = "c7a1e4b90f22"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media_assets", sa.Column("blob", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("media_assets", "blob")
