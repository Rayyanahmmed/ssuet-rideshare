"""profile photos

Revision ID: 9d31c4f8a2b7
Revises: 1ecaa4a7e72e
Create Date: 2026-11-06 18:45:00.000000

Phase 13: a member's avatar becomes an uploaded `media_assets` row instead of a link
pasted from somewhere else. `ON DELETE SET NULL` keeps a deleted asset from taking the
account with it.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '9d31c4f8a2b7'
down_revision: str | None = '1ecaa4a7e72e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('profile_photo_asset_id', sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f('fk_users_profile_photo_asset_id_media_assets'),
            'media_assets',
            ['profile_photo_asset_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f('fk_users_profile_photo_asset_id_media_assets'), type_='foreignkey'
        )
        batch_op.drop_column('profile_photo_asset_id')
