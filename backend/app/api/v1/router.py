"""API v1 router aggregation (§19).

Routers are registered phase by phase. Only modules that already exist are
imported, so the API surface is always internally consistent and runnable.
"""

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    app_download,
    auth,
    chat,
    health,
    maps,
    notifications,
    reports,
    requests,
    reviews,
    rides,
    trips,
    uploads,
    users,
    vehicles,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(maps.router)
api_router.include_router(app_download.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(vehicles.router)
api_router.include_router(rides.router)
api_router.include_router(requests.router)
api_router.include_router(requests.ride_router)
api_router.include_router(trips.router)
api_router.include_router(chat.router)
api_router.include_router(notifications.router)
api_router.include_router(admin.router)
api_router.include_router(reviews.router)
api_router.include_router(reports.router)
api_router.include_router(uploads.router)
