"""photo reports

Revision ID: b4f0a91c73de
Revises: 9d31c4f8a2b7
Create Date: 2026-11-07 07:30:00.000000

Phase 15: a report can point at a specific uploaded picture. The foreign key is
SET NULL so deleting an asset never deletes the complaint that mentioned it.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b4f0a91c73de'
down_revision: str | None = '9d31c4f8a2b7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('reports', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reported_photo_asset_id', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('photo_reason', sa.String(length=32), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f('fk_reports_reported_photo_asset_id_media_assets'),
            'media_assets',
            ['reported_photo_asset_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('reports', schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f('fk_reports_reported_photo_asset_id_media_assets'), type_='foreignkey'
        )
        batch_op.drop_column('photo_reason')
        batch_op.drop_column('reported_photo_asset_id')
