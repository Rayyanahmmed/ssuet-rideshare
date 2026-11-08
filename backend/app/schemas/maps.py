"""Map integration schemas (§13, §16)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MapProviderName = Literal["osm", "geoapify", "maptiler"]


class MapClientConfigOut(BaseModel):
    """What the app needs — and nothing it could abuse. The API key is never included."""

    enabled: bool
    provider: str
    style: str
    needs_key: bool
    has_key: bool
    attribution: str
    tile_url_template: str = Field(description="Tiles are served by this API, never by the provider")
    updated_at: str | None = None


class ProviderOption(BaseModel):
    value: str
    needs_key: bool
    default_style: str


class AdminMapSettingsOut(BaseModel):
    provider: str
    style: str
    enabled: bool
    has_key: bool
    needs_key: bool
    attribution: str
    updated_at: str | None = None
    updated_by: str | None = None
    available_providers: list[ProviderOption] = []


class AdminMapSettingsIn(BaseModel):
    provider: MapProviderName | None = None
    style: str | None = Field(default=None, max_length=60)
    enabled: bool | None = None
    api_key: str | None = Field(
        default=None,
        max_length=200,
        description="Omit to keep the stored key, send an empty string to clear it.",
    )


class MapTestOut(BaseModel):
    ok: bool
    provider: str
    reason: str
    latency_ms: int | None = None


class GeoResultOut(BaseModel):
    label: str
    latitude: float
    longitude: float
