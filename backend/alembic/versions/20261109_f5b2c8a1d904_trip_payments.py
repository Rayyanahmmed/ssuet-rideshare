"""trip_payments: cash payment record, invoice number and non-payment link.

Revision ID: f5b2c8a1d904
Revises: e3c9b7d1a426
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "f5b2c8a1d904"
down_revision = "e3c9b7d1a426"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trip_payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trip_id", sa.Uuid(), nullable=False),
        sa.Column("driver_id", sa.Uuid(), nullable=False),
        sa.Column("passenger_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("amount_pkr", sa.Integer(), nullable=True),
        sa.Column("invoice_number", sa.String(length=40), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("non_payment_report_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("amount_pkr IS NULL OR amount_pkr >= 0", name="payment_amount_non_negative"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["driver_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["passenger_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["non_payment_report_id"], ["reports.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id", name="uq_trip_payments_trip_id"),
        sa.UniqueConstraint("invoice_number", name="uq_trip_payments_invoice_number"),
    )
    op.create_index("ix_trip_payments_created_at", "trip_payments", ["created_at"])
    op.create_index("ix_trip_payments_driver_id", "trip_payments", ["driver_id"])
    op.create_index("ix_trip_payments_passenger_id", "trip_payments", ["passenger_id"])


def downgrade() -> None:
    op.drop_index("ix_trip_payments_passenger_id", table_name="trip_payments")
    op.drop_index("ix_trip_payments_driver_id", table_name="trip_payments")
    op.drop_index("ix_trip_payments_created_at", table_name="trip_payments")
    op.drop_table("trip_payments")
