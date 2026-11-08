"""Map provider configuration and tile/geocode proxying (§13).

Why a proxy and not a key in the app:

* An API key shipped inside an APK is public — it can be extracted and its quota burned.
* A key baked at build time can only be rotated by shipping a new APK. The map broke that way
  once already: the release APK carried a dead Google key and every screen stayed blank.

Here the credential lives in the database (encrypted at rest), an administrator rotates it in
the console, and the app only ever talks to **our** `/maps/tiles/...` and `/maps/search`
endpoints. Rotating the key therefore needs no rebuild, and the key never leaves the server.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Literal

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.app_setting import AppSetting
from app.models.user import User

logger = logging.getLogger("ssuet.rideshare.maps")

MapProvider = Literal["osm", "geoapify", "maptiler"]

PROVIDER_KEY = "maps.provider"
STYLE_KEY = "maps.style"
API_KEY_KEY = "maps.api_key_enc"
ENABLED_KEY = "maps.enabled"

OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
GEOAPIFY_ATTRIBUTION = 'Powered by <a href="https://www.geoapify.com/">Geoapify</a> · ' + OSM_ATTRIBUTION
MAPTILER_ATTRIBUTION = '&copy; <a href="https://www.maptiler.com/">MapTiler</a> · ' + OSM_ATTRIBUTION

# A tile over SSUET / Gulshan-e-Iqbal. The "Test" button uses this rather than a z=0 world
# tile, because providers happily serve low zooms even with an invalid key — a world tile
# would report success while every real map view failed.
PROBE_TILE = (12, 2811, 1755)

USER_AGENT = "SSUET-RideShare/1.0 (campus rideshare project; contact: admin@ssuet.edu.pk)"

class MapProviderError(RuntimeError):
    """The provider answered, but not with a usable tile (bad key, quota, outage)."""


# provider -> (tile URL template, default style, needs key?, attribution)
PROVIDERS: dict[str, tuple[str, str, bool, str]] = {
    "osm": ("https://tile.openstreetmap.org/{z}/{x}/{y}.png", "standard", False, OSM_ATTRIBUTION),
    "geoapify": (
        "https://maps.geoapify.com/v1/tile/{style}/{z}/{x}/{y}.png?apiKey={key}",
        "osm-bright",
        True,
        GEOAPIFY_ATTRIBUTION,
    ),
    "maptiler": (
        "https://api.maptiler.com/maps/{style}/{z}/{x}/{y}.png?key={key}",
        "streets-v2",
        True,
        MAPTILER_ATTRIBUTION,
    ),
}

_TILE_CACHE: dict[tuple[str, int, int, int], tuple[float, bytes, str]] = {}
_TILE_CACHE_TTL = 600.0
_TILE_CACHE_MAX = 400


# ------------------------------------------------------------------ crypto
def _fernet() -> Fernet:
    """Derive a stable Fernet key from SECRET_KEY (32 bytes, url-safe base64)."""
    digest = hashlib.sha256(f"maps-api-key::{settings.JWT_SECRET_KEY}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_key(raw: str) -> str:
    return _fernet().encrypt(raw.encode()).decode()


def decrypt_key(stored: str) -> str:
    try:
        return _fernet().decrypt(stored.encode()).decode()
    except (InvalidToken, ValueError):
        # SECRET_KEY changed (fresh dev database, rotated secret) — treat as "no key".
        logger.warning("Stored map API key could not be decrypted; ignoring it.")
        return ""


# ------------------------------------------------------------------ storage
def _get(db: Session, key: str) -> str | None:
    row = db.get(AppSetting, key)
    return row.value if row else None


def _set(db: Session, key: str, value: str, actor: User | None) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value, updated_by_id=actor.id if actor else None)
        db.add(row)
    else:
        row.value = value
        if actor is not None:
            row.updated_by_id = actor.id
    db.flush()


@dataclass(frozen=True)
class MapConfig:
    provider: MapProvider
    style: str
    enabled: bool
    has_key: bool
    needs_key: bool
    attribution: str
    api_key: str
    updated_at: str | None


def get_config(db: Session) -> MapConfig:
    """Effective configuration: database first, then environment, then the OSM default."""
    provider = (_get(db, PROVIDER_KEY) or settings.MAP_PROVIDER or "osm").strip().lower()
    if provider not in PROVIDERS:
        provider = "osm"
    default_style = PROVIDERS[provider][1]
    style = (_get(db, STYLE_KEY) or default_style).strip() or default_style
    enabled_raw = _get(db, ENABLED_KEY)
    enabled = True if enabled_raw is None else enabled_raw == "1"

    stored = _get(db, API_KEY_KEY)
    api_key = decrypt_key(stored) if stored else ""
    if not api_key and provider == "geoapify":
        api_key = settings.GEOAPIFY_API_KEY.strip()

    row = db.get(AppSetting, PROVIDER_KEY)
    updated_at = row.updated_at.isoformat() if row and row.updated_at else None

    return MapConfig(
        provider=provider,  # type: ignore[arg-type]
        style=style,
        enabled=enabled,
        has_key=bool(api_key),
        needs_key=PROVIDERS[provider][2],
        attribution=PROVIDERS[provider][3],
        api_key=api_key,
        updated_at=updated_at,
    )


def update_config(
    db: Session,
    *,
    actor: User,
    provider: str | None = None,
    style: str | None = None,
    api_key: str | None = None,
    enabled: bool | None = None,
) -> MapConfig:
    """`api_key=None` keeps the stored key; `api_key=""` clears it."""
    if provider is not None:
        normalised = provider.strip().lower()
        if normalised not in PROVIDERS:
            raise ValueError(f"Unknown map provider '{provider}'. Use one of: {', '.join(PROVIDERS)}.")
        _set(db, PROVIDER_KEY, normalised, actor)
    if style is not None:
        _set(db, STYLE_KEY, style.strip(), actor)
    if enabled is not None:
        _set(db, ENABLED_KEY, "1" if enabled else "0", actor)
    if api_key is not None:
        _set(db, API_KEY_KEY, encrypt_key(api_key.strip()) if api_key.strip() else "", actor)

    db.commit()
    _TILE_CACHE.clear()  # a new provider/key must not serve the previous provider's tiles
    return get_config(db)


# ------------------------------------------------------------------ tiles
def tile_url(config: MapConfig, z: int, x: int, y: int) -> str:
    template = PROVIDERS[config.provider][0]
    return template.format(style=config.style, z=z, x=x, y=y, key=config.api_key)


@dataclass
class TileResult:
    """A tile plus the truth about where it came from."""

    content: bytes
    content_type: str
    provider: str
    fell_back: bool
    primary_error: str | None = None


def _fetch_from(config: MapConfig, z: int, x: int, y: int) -> tuple[bytes, str]:
    cache_key = (config.provider, z, x, y)
    cached = _TILE_CACHE.get(cache_key)
    if cached and (time.time() - cached[0]) < _TILE_CACHE_TTL:
        return cached[1], cached[2]

    response = httpx.get(
        tile_url(config, z, x, y),
        timeout=10.0,
        headers={"User-Agent": USER_AGENT, "Accept": "image/png,image/*"},
        follow_redirects=True,
    )
    if response.status_code >= 400:
        # Providers answer an invalid/expired key with JSON, not an image: surface the reason
        # verbatim so the admin console can say why the map is blank.
        reason = ""
        try:
            reason = str(response.json().get("message") or response.json().get("error") or "")
        except Exception:
            reason = response.text[:120]
        hint = " (check the API key / quota)" if response.status_code in (401, 403, 429) else ""
        raise MapProviderError(f"Provider replied {response.status_code} {reason}{hint}".strip())

    content_type = response.headers.get("content-type", "image/png").split(";")[0]
    if not content_type.startswith("image/"):
        raise MapProviderError(f"Provider returned {content_type} instead of an image")
    if len(_TILE_CACHE) >= _TILE_CACHE_MAX:
        _TILE_CACHE.clear()
    _TILE_CACHE[cache_key] = (time.time(), response.content, content_type)
    return response.content, content_type


def _osm_fallback_config() -> MapConfig:
    return MapConfig(
        provider="osm",
        style="standard",
        enabled=True,
        has_key=False,
        needs_key=False,
        attribution=OSM_ATTRIBUTION,
        api_key="",
        updated_at=None,
    )


def fetch_tile(db: Session, z: int, x: int, y: int) -> TileResult:
    """Serve a tile, and never leave the map blank.

    A paid tier can run out, a key can be revoked, a provider can have an outage. In any of
    those cases the map falls back to OpenStreetMap — which needs no credential — instead of
    drawing an empty rectangle like the old build-time Google key did. The fallback is
    reported to the caller (and logged) so the admin console can say what happened.
    """
    config = get_config(db)
    if not config.enabled:
        raise PermissionError("Map tiles are disabled in the admin console.")

    primary_error: str | None = None
    if config.needs_key and not config.has_key:
        primary_error = f"{config.provider} has no API key stored in the admin console"
    else:
        try:
            content, content_type = _fetch_from(config, z, x, y)
            return TileResult(content, content_type, config.provider, False)
        except MapProviderError as exc:
            primary_error = str(exc)
        except Exception as exc:  # DNS, timeout, TLS
            primary_error = f"{type(exc).__name__}: {exc}"

    if config.provider != "osm":
        logger.warning("Map fallback to OpenStreetMap for %s/%s/%s — %s", z, x, y, primary_error)
        content, content_type = _fetch_from(_osm_fallback_config(), z, x, y)
        return TileResult(content, content_type, "osm", True, primary_error)

    raise MapProviderError(primary_error or "OpenStreetMap is unreachable right now")


GEOCODE_CHECKS = {
    "geoapify": "https://api.geoapify.com/v1/geocode/search",
    "maptiler": "https://api.maptiler.com/geocoding/Gulshan-e-Iqbal.json",
}


def validate_key(config: MapConfig) -> tuple[bool, str]:
    """Ask the provider's geocoder about the key — the one place a dead key is always refused.

    Tile endpoints are generous (Geoapify even serves its free styles with no key at all), so a
    tile fetch proves nothing about the credential. The geocoder does answer `401 Invalid
    apiKey`, which is exactly the message an administrator needs to see.
    """
    url = GEOCODE_CHECKS.get(config.provider)
    if url is None:
        return True, "no key required"
    try:
        if config.provider == "geoapify":
            response = httpx.get(
                url,
                params={"text": "Gulshan-e-Iqbal Karachi", "limit": 1, "apiKey": config.api_key},
                timeout=10.0,
                headers={"User-Agent": USER_AGENT},
            )
        else:
            response = httpx.get(
                url, params={"key": config.api_key, "limit": 1}, timeout=10.0, headers={"User-Agent": USER_AGENT}
            )
    except Exception as exc:
        return False, f"could not reach {config.provider}: {type(exc).__name__}"

    if response.status_code in (401, 403):
        reason = ""
        try:
            reason = str(response.json().get("message") or response.json().get("error") or "")
        except Exception:
            reason = response.text[:100]
        return False, f"key rejected ({response.status_code} {reason})".strip()
    if response.status_code == 429:
        return False, "key is valid but the plan's rate limit / quota is exhausted (429)"
    if response.status_code >= 400:
        return False, f"provider replied {response.status_code}"
    return True, "key accepted"


def test_connection(db: Session) -> dict:
    """What the admin "Test" button reports: is the credential real, and is the map drawn?"""
    started = time.perf_counter()
    config = get_config(db)
    z, x, y = PROBE_TILE
    _TILE_CACHE.pop((config.provider, z, x, y), None)  # never answer from cache
    _TILE_CACHE.pop(("osm", z, x, y), None)

    if not config.enabled:
        return {"ok": False, "reason": "Maps are switched off in this console.", "latency_ms": None,
                "provider": config.provider}

    key_ok, key_reason = (True, "no key required")
    if config.needs_key:
        if not config.has_key:
            return {
                "ok": False,
                "reason": f"{config.provider} needs an API key and none is stored — the app shows "
                "OpenStreetMap tiles until you add one.",
                "latency_ms": None,
                "provider": config.provider,
            }
        key_ok, key_reason = validate_key(config)

    try:
        result = fetch_tile(db, z, x, y)
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"no tile: {type(exc).__name__}: {exc}",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "provider": config.provider,
        }

    latency = int((time.perf_counter() - started) * 1000)
    if result.fell_back:
        return {
            "ok": False,
            "reason": f"key/credential rejected ({key_reason}); the app is being served OpenStreetMap "
            f"tiles instead, so the map still works. Provider said: {result.primary_error}",
            "latency_ms": latency,
            "provider": config.provider,
        }

    reason = f"Karachi tile received ({len(result.content)} bytes) · {key_reason}"
    return {"ok": key_ok, "reason": reason, "latency_ms": latency, "provider": config.provider}


# ------------------------------------------------------------------ geocoding
def search_places(db: Session, query: str, limit: int = 5) -> list[dict]:
    """Free-text place search, proxied so the key stays on the server."""
    config = get_config(db)
    if config.provider == "geoapify" and config.has_key:
        response = httpx.get(
            "https://api.geoapify.com/v1/geocode/search",
            params={"text": query, "limit": limit, "filter": "countrycode:pk", "apiKey": config.api_key},
            timeout=10.0,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        features = response.json().get("features", [])
        return [
            {
                "label": f.get("properties", {}).get("formatted", "")[:160],
                "latitude": f["properties"]["lat"],
                "longitude": f["properties"]["lon"],
            }
            for f in features
        ]

    # OSM / MapTiler default: Nominatim (usage policy allows light, identified traffic).
    response = httpx.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": query, "format": "jsonv2", "limit": limit, "countrycodes": "pk", "addressdetails": 0},
        timeout=10.0,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return [
        {"label": row.get("display_name", "")[:160], "latitude": float(row["lat"]), "longitude": float(row["lon"])}
        for row in response.json()
    ]


def reverse_geocode(db: Session, latitude: float, longitude: float) -> dict:
    config = get_config(db)
    if config.provider == "geoapify" and config.has_key:
        response = httpx.get(
            "https://api.geoapify.com/v1/geocode/reverse",
            params={"lat": latitude, "lon": longitude, "apiKey": config.api_key},
            timeout=10.0,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        features = response.json().get("features", [])
        label = features[0]["properties"].get("formatted", "") if features else ""
        return {"label": label[:160], "latitude": latitude, "longitude": longitude}

    response = httpx.get(
        "https://nominatim.openstreetmap.org/reverse",
        params={"lat": latitude, "lon": longitude, "format": "jsonv2"},
        timeout=10.0,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "label": (payload.get("display_name") or "")[:160],
        "latitude": latitude,
        "longitude": longitude,
    }


def admin_settings_row(db: Session) -> dict:
    config = get_config(db)
    row = db.scalar(select(AppSetting).where(AppSetting.key == PROVIDER_KEY))
    return {
        "provider": config.provider,
        "style": config.style,
        "enabled": config.enabled,
        "has_key": config.has_key,
        "needs_key": config.needs_key,
        "attribution": config.attribution,
        "updated_at": config.updated_at,
        "updated_by": (row.updated_by.full_name if row and row.updated_by else None),
        "available_providers": [
            {"value": name, "needs_key": meta[2], "default_style": meta[1]} for name, meta in PROVIDERS.items()
        ],
    }
