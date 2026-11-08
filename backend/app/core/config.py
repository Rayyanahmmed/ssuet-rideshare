"""Application settings, loaded and validated from the environment.

Every configuration value used by the backend lives here (§20). Nothing is
hardcoded in the application source, and no secret is ever echoed to logs.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production", "test"]

PLACEHOLDER_PREFIXES = ("CHANGE_ME", "YOUR_", "changeme")


class Settings(BaseSettings):
    """Typed, validated view of the process environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- Application ----------
    PROJECT_NAME: str = "SSUET RideShare API"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: Environment = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # ---------- Database ----------
    DATABASE_URL: str = "sqlite+pysqlite:///./ssuet_dev.db"
    DB_ECHO: bool = False
    # Development convenience only: create tables on boot when no migration was
    # run yet. Alembic remains the single owner of schema changes (§18).
    AUTO_CREATE_TABLES: bool = True
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # ---------- JWT ----------
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ---------- Admin bootstrap (§17) ----------
    ADMIN_NAME: str = "System Administrator"
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = ""
    ADMIN_BOOTSTRAP_ENABLED: bool = False

    # ---------- Email delivery (verification / password reset) ----------
    # When SMTP_HOST is empty the backend uses the development console backend
    # (the message is logged instead of sent). See documentation/06.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    EMAIL_FROM: str = "SSUET RideShare <no-reply@ssuet-rideshare.local>"
    # Links placed inside transactional emails (mobile deep link + admin origin).
    APP_DEEP_LINK_BASE: str = "ssuetrideshare://"
    ADMIN_WEB_URL: str = "http://localhost:5173"

    # ---------- University verification ----------
    UNIVERSITY_EMAIL_DOMAINS: str = "ssuet.edu.pk"
    AUTO_VERIFY_UNIVERSITY_EMAILS: bool = True

    # ---------- Maps (§13) ----------
    # The map provider is chosen in the admin console → Map API, and its key is stored
    # encrypted in the database, so rotation never needs a rebuild. These environment
    # values only seed a fresh install / act as a fallback when nothing is stored yet.
    MAP_PROVIDER: str = "osm"           # osm | geoapify | maptiler
    GEOAPIFY_API_KEY: str = ""          # used only while no key is stored in the database
    SSUET_LATITUDE: float = 24.9372
    SSUET_LONGITUDE: float = 67.1138

    # ---------- Observability (§23, Phase 12) ----------
    # A request slower than this is logged as a warning with its request id, so a slow
    # endpoint can be found in the logs instead of being guessed at.
    SLOW_REQUEST_MS: int = Field(default=500, ge=50, le=60000)

    # ---------- Uploaded media (§4, §16, Phase 9) ----------
    # New uploads are stored in the database (media_assets.blob). MEDIA_ROOT only holds
    # legacy files written before that change. Files are served through GET /media/{id}
    # (owner or admin only), never as a public static directory, because verification
    # documents are personal data.
    MEDIA_ROOT: str = "./media"
    MAX_UPLOAD_BYTES: int = Field(default=5 * 1024 * 1024, ge=64 * 1024, le=25 * 1024 * 1024)
    # A profile picture is a thumbnail, not a document scan: images only, 2 MB.
    MAX_PROFILE_PHOTO_BYTES: int = Field(default=2 * 1024 * 1024, ge=64 * 1024, le=10 * 1024 * 1024)
    # Phase 14 — profile photos are normalised on upload: decoded, auto-oriented, cropped
    # square, resized and re-encoded. That strips EXIF (including GPS) and makes a phone
    # photo cheap to serve to every member.
    PROFILE_PHOTO_MAX_DIMENSION: int = Field(default=512, ge=64, le=2048)
    PROFILE_PHOTO_THUMB_DIMENSION: int = Field(default=128, ge=32, le=512)
    PROFILE_PHOTO_WEBP_QUALITY: int = Field(default=82, ge=40, le=95)
    # A 40 MP ceiling refuses decompression bombs: a 250 KB PNG can claim 30000×30000
    # pixels, which is 3.6 GB once decoded.
    MAX_PHOTO_PIXELS: int = Field(default=40_000_000, ge=1_000_000)
    # Uploads that no record references are deleted by the housekeeping sweep once they
    # are this old. The window protects a file that is still mid-flow (member picked a
    # photo but has not submitted the form yet).
    MEDIA_ORPHAN_RETENTION_DAYS: int = Field(default=7, ge=1, le=365)

    # ---------- CORS / rate limiting ----------
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:8081"
    RATE_LIMIT_ENABLED: bool = True

    # ---------- Push notifications ----------
    EXPO_PUSH_ENABLED: bool = True
    # Optional. Only needed when the Expo project has "Enhanced push security" on:
    # without it Expo answers 401 and every send is logged as a warning.
    EXPO_ACCESS_TOKEN: str = ""
    EXPO_PUSH_URL: str = "https://exp.host/--/api/v2/push/send"

    # ---------- Business rules (§9) ----------
    MAX_CONFIRMED_PASSENGERS: int = Field(default=1, ge=1, le=8)
    UNIVERSITY_AREA_LABEL: str = "SSUET, University Road, Karachi"
    # Trust policy: block publishing when a vehicle has been rejected. Set to true
    # to also require a *verified* vehicle (stricter, but slower for new drivers).
    REQUIRE_VERIFIED_VEHICLE_FOR_PUBLISH: bool = False
    # Two journeys by the same driver may not start within this window (§7 sanity rule)
    MIN_MINUTES_BETWEEN_DRIVER_RIDES: int = 30
    # Radius default for "nearby" discovery
    DEFAULT_DISCOVERY_RADIUS_KM: float = 25.0
    PASSWORD_MIN_LENGTH: int = Field(default=8, ge=8, le=64)
    EMAIL_VERIFICATION_TOKEN_MINUTES: int = 60 * 24
    PASSWORD_RESET_TOKEN_MINUTES: int = 30
    RIDE_AUTO_EXPIRE_GRACE_MINUTES: int = 60
    # In-process housekeeping cadence (§10). 0 disables the scheduler — in a
    # multi-worker deployment run `python -m scripts.expire_stale_rides` from cron
    # instead, so the API processes stay stateless.
    MAINTENANCE_INTERVAL_MINUTES: int = Field(default=15, ge=0, le=1440)

    # ---------------- derived helpers ----------------
    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def university_domains(self) -> list[str]:
        return [d.strip().lower().lstrip("@") for d in self.UNIVERSITY_EMAIL_DOMAINS.split(",") if d.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT in ("production", "staging")

    @property
    def smtp_configured(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAIL_FROM)

    @property
    def media_root(self) -> str:
        return str(Path(self.MEDIA_ROOT).expanduser())

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    # ---------------- validation ----------------
    @field_validator("LOG_LEVEL")
    @classmethod
    def _valid_log_level(cls, v: str) -> str:
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        v = v.upper()
        if v not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def _valid_db_url(cls, v: str) -> str:
        # Hosting providers (Neon, Render) hand out "postgres://" or "postgresql://" URLs.
        # The app uses the psycopg 3 driver, so normalise those to the explicit driver name.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                v = "postgresql+psycopg://" + v[len(prefix):]
                break
        if not v.startswith(("postgresql+psycopg://", "sqlite+pysqlite://", "sqlite:///")):
            raise ValueError("DATABASE_URL must be a postgresql:// (Neon) or sqlite URL")
        return v

    @model_validator(mode="after")
    def _security_checks(self) -> "Settings":
        """Fail fast on insecure configuration; stay friendly in development."""
        secret = self.JWT_SECRET_KEY
        if self.is_production:
            if not secret or secret.upper().startswith(PLACEHOLDER_PREFIXES) or len(secret) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be set to a random value of >= 32 characters in "
                    "production. Generate one with: python -c \"import secrets;print(secrets.token_urlsafe(48))\""
                )
            if self.ADMIN_BOOTSTRAP_ENABLED and not self.ADMIN_PASSWORD:
                raise ValueError("ADMIN_PASSWORD is required while ADMIN_BOOTSTRAP_ENABLED is true")
        else:
            if not secret:
                # Development convenience only: an ephemeral secret (tokens die on restart).
                object.__setattr__(self, "JWT_SECRET_KEY", secrets.token_urlsafe(48))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
