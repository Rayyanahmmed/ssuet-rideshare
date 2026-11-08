"""Shared schema helpers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """Base for response models read straight from SQLAlchemy objects."""

    # populate_by_name lets a schema read a *different* attribute than it exposes
    # (`profile_photo_url` ← `User.photo_url`, see schemas/user.py).
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MessageOut(BaseModel):
    """Generic acknowledgement used by fire-and-forget endpoints."""

    message: str
    detail: str | None = None


class PageMeta(BaseModel):
    total: int
    page: int
    page_size: int
    has_next: bool
