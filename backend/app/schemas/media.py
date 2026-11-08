"""Media upload schemas (§4, §16, Phase 9)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.config import settings
from app.models.media import MediaAsset


class MediaAssetOut(BaseModel):
    """What the client needs to reference an upload; never the storage path."""

    id: uuid.UUID
    purpose: str
    content_type: str
    byte_size: int
    checksum_sha256: str
    original_filename: str | None = None
    url: str
    created_at: datetime

    @classmethod
    def from_asset(cls, asset: MediaAsset) -> "MediaAssetOut":
        return cls(
            id=asset.id,
            purpose=asset.purpose,
            content_type=asset.content_type,
            byte_size=asset.byte_size,
            checksum_sha256=asset.checksum_sha256,
            original_filename=asset.original_filename,
            url=f"{settings.API_V1_PREFIX}/media/{asset.id}",
            created_at=asset.created_at,
        )
