"""Map endpoints (§13).

The mobile app never holds a map provider credential: it loads tiles and searches places
through this router, so rotating the key in the admin console takes effect immediately —
no rebuild, no `.env` edit, no app update.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession
from app.schemas.maps import GeoResultOut, MapClientConfigOut
from app.services import map_service

router = APIRouter(prefix="/maps", tags=["Maps"])


@router.get("/config", response_model=MapClientConfigOut, summary="Which map provider the app should render")
def map_config(db: DbSession) -> MapClientConfigOut:
    config = map_service.get_config(db)
    return MapClientConfigOut(
        enabled=config.enabled,
        provider=config.provider,
        style=config.style,
        needs_key=config.needs_key,
        has_key=config.has_key,
        attribution=config.attribution,
        tile_url_template="/api/v1/maps/tiles/{z}/{x}/{y}.png",
        updated_at=config.updated_at,
    )


@router.get(
    "/tiles/{z}/{x}/{y}.png",
    summary="Map tile proxy",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}, 503: {"description": "Maps disabled or key missing"}},
)
def map_tile(db: DbSession, z: int, x: int, y: int) -> Response:
    if z < 0 or z > 22 or x < 0 or y < 0:
        raise HTTPException(status_code=404, detail="Tile out of range.")
    try:
        tile = map_service.fetch_tile(db, z, x, y)
    except PermissionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except map_service.MapProviderError as exc:
        raise HTTPException(status_code=502, detail=f"No map provider could serve this tile: {exc}") from exc
    except Exception as exc:  # DNS, timeout, TLS
        raise HTTPException(status_code=502, detail=f"Map provider unreachable: {type(exc).__name__}") from exc

    headers = {
        "Cache-Control": "public, max-age=86400",
        "X-Map-Provider": tile.provider,
        # Set when the configured provider failed and OpenStreetMap stepped in — the map keeps
        # working and the console can tell the administrator why.
        "X-Map-Fallback": "1" if tile.fell_back else "0",
        "Access-Control-Expose-Headers": "X-Map-Provider, X-Map-Fallback",
    }
    return Response(content=tile.content, media_type=tile.content_type, headers=headers)


@router.get("/search", response_model=list[GeoResultOut], summary="Place search (proxied, authenticated)")
def map_search(
    current_user: CurrentUser,
    db: DbSession,
    q: str = Query(min_length=2, max_length=120),
    limit: int = Query(default=5, ge=1, le=10),
) -> JSONResponse:
    try:
        return JSONResponse(map_service.search_places(db, q, limit=limit))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Place search unavailable: {type(exc).__name__}") from exc


@router.get("/reverse", response_model=GeoResultOut, summary="Coordinates → area name (proxied, authenticated)")
def map_reverse(
    current_user: CurrentUser,
    db: DbSession,
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
) -> dict:
    try:
        return map_service.reverse_geocode(db, lat, lng)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Reverse geocode unavailable: {type(exc).__name__}") from exc
