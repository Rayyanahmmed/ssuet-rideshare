"""Health, readiness and client bootstrap metadata endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import settings
from app.db.session import get_db

router = APIRouter(tags=["System"])


@router.get("/health", summary="Liveness probe")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": __version__, "environment": settings.ENVIRONMENT}


@router.get("/health/ready", summary="Readiness probe (checks the database)")
def readiness(db: Session = Depends(get_db)) -> dict[str, Any]:
    db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}


@router.get("/meta", summary="Static client configuration")
def meta(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Everything the mobile app needs to render the university card and its feature flags.

    `maps_configured` is read from the live map configuration, which an administrator can
    change in the console (Map API) without a rebuild (§13).
    """
    from app.services import map_service

    try:
        map_config = map_service.get_config(db)
        maps_ready = map_config.enabled and (not map_config.needs_key or map_config.has_key)
    except Exception:  # table not migrated yet — do not break the bootstrap endpoint
        maps_ready = True
    return {
        "university": {
            "name": "Sir Syed University of Engineering & Technology",
            "short_name": "SSUET",
            "latitude": settings.SSUET_LATITUDE,
            "longitude": settings.SSUET_LONGITUDE,
            "default_area_label": "SSUET, University Road, Karachi",
        },
        "features": {
            "maps_configured": maps_ready,
            "push_notifications": settings.EXPO_PUSH_ENABLED,
            "max_confirmed_passengers": settings.MAX_CONFIRMED_PASSENGERS,
        },
        "environment": settings.ENVIRONMENT,
    }
