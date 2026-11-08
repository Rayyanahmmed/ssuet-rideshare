"""Immutable administrative action log (§16, §22)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_column
from app.models.enums import AdminActionType

if TYPE_CHECKING:
    from app.models.report import Report
    from app.models.user import User


class AdminAction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "admin_actions"
    __table_args__ = (Index("ix_admin_actions_admin_created", "admin_id", "created_at"),)

    admin_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action_type: Mapped[AdminActionType] = mapped_column(enum_column(AdminActionType, 32), nullable=False)
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reports.id", ondelete="SET NULL"), nullable=True
    )
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    admin: Mapped["User | None"] = relationship(foreign_keys=[admin_id])
    report: Mapped["Report | None"] = relationship(back_populates="admin_actions")
