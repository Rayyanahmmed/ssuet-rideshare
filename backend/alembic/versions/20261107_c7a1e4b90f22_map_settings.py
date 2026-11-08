"""runtime map provider settings (rotatable API key)

Revision ID: c7a1e4b90f22
Revises: b4f0a91c73de
Create Date: 2026-11-07

The map credential used to be a build-time constant in the APK (Google Maps SDK), so an
expired key meant a blank map for everyone until a new build shipped. It now lives here,
is editable from the admin console, and is stored encrypted (Fernet / SECRET_KEY).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c7a1e4b90f22"
down_revision = "b4f0a91c73de"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index("ix_app_settings_created_at", "app_settings", ["created_at"])

    # Seed the safe default: OpenStreetMap needs no credential, so a fresh install always
    # has a working map and an administrator can switch provider later.
    op.execute(
        sa.text(
            "INSERT INTO app_settings (key, value, created_at, updated_at) "
            "VALUES ('maps.provider', 'osm', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO app_settings (key, value, created_at, updated_at) "
            "VALUES ('maps.enabled', '1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_app_settings_created_at", table_name="app_settings")
    op.drop_table("app_settings")
