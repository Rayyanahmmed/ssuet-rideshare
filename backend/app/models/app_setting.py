"""Runtime-editable platform settings (§16, §17).

Integrations whose credentials rotate (map tiles, and later mail or push) must not be baked
into the app or into a deployed `.env`: an administrator edits them in the console and every
client picks the change up on its next request. Values live here, one row per key.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    """Dotted key, e.g. `maps.provider` or `maps.api_key_enc` (never plaintext)."""

    value: Mapped[str] = mapped_column(Text, nullable=False, default="")

    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    updated_by: Mapped[User | None] = relationship("User", lazy="joined")
