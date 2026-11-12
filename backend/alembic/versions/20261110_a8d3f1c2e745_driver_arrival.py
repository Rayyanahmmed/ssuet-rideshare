"""trips.driver_arrived_at: driver marks arrival at the meeting point.

Revision ID: a8d3f1c2e745
Revises: f5b2c8a1d904
Create Date: 2026-11-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a8d3f1c2e745"
down_revision = "f5b2c8a1d904"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("driver_arrived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "driver_arrived_at")
