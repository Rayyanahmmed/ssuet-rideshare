"""DATABASE_URL normalisation: hosting providers hand out plain postgresql:// URLs."""

import pytest

from app.core.config import Settings


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("postgresql://u:p@ep-x.neon.tech/db?sslmode=require", "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=require"),
        ("postgres://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ],
)
def test_postgres_urls_use_psycopg_driver(raw, expected):
    assert Settings(DATABASE_URL=raw).DATABASE_URL == expected


def test_sqlite_dev_url_is_kept():
    assert Settings(DATABASE_URL="sqlite+pysqlite:///./ssuet_dev.db").DATABASE_URL == "sqlite+pysqlite:///./ssuet_dev.db"


def test_unknown_scheme_is_rejected():
    with pytest.raises(ValueError):
        Settings(DATABASE_URL="mysql://u:p@host/db")
