"""Engine + session factory.

PostgreSQL is the target database; SQLite is supported so that the project can
be booted with zero external services during development and CI.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_SQLITE_CORRUPT_HINT = (
    "SQLite database unusable: {reason}.\n"
    "This is only the development database — nothing is lost by rebuilding it:\n"
    "  1. stop the server\n"
    "  2. delete {path} (and any {name}-wal / {name}-shm next to it)\n"
    "  3. start the server again — the schema is recreated because AUTO_CREATE_TABLES=true\n"
    "  4. optional: python -m scripts.seed  (demo members, rides, trips, reviews)\n"
    "If it keeps happening, the file is probably being synced by OneDrive/Dropbox while the "
    "server writes to it: move the project (or set DATABASE_URL) outside the synced folder."
)


def sqlite_database_path() -> Path | None:
    """Filesystem path of the SQLite database, or None when the URL is not a file URL."""
    url = settings.DATABASE_URL
    if not url.startswith("sqlite"):
        return None
    _, _, raw = url.partition(":///")
    if not raw or raw == ":memory:":
        return None
    return Path(raw).expanduser().resolve()


if settings.is_sqlite:
    engine: Engine = create_engine(
        settings.DATABASE_URL,
        echo=settings.DB_ECHO,
        future=True,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - driver hook
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")   # real FK enforcement in SQLite
            cursor.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError as exc:
            # A corrupted dev database otherwise fails with a 60-line SQLAlchemy traceback
            # that says nothing about what to do (see documentation/24 §5f).
            path = sqlite_database_path()
            raise RuntimeError(
                _SQLITE_CORRUPT_HINT.format(
                    reason=exc,
                    path=path or settings.DATABASE_URL,
                    name=(path.name if path else "the database file"),
                )
            ) from exc
        finally:
            cursor.close()
else:
    engine = create_engine(
        settings.DATABASE_URL,
        echo=settings.DB_ECHO,
        future=True,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed.

    Teardown is also where queued Expo pushes are flushed: by then the handler has
    committed, so only notifications that really exist are announced (§12).
    """
    from app.services import push_service  # local import avoids a circular import

    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            push_service.flush_pending(db)
        except Exception:  # pushing must never break a response
            pass
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Transactional scope for scripts, background tasks and services."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
