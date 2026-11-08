"""Reusable column type helpers."""

from __future__ import annotations

from enum import Enum

from sqlalchemy import Enum as SAEnum


def enum_column(enum_cls: type[Enum], length: int = 32, **kwargs):
    """VARCHAR-backed enum: portable, no PostgreSQL type creation required.

    Values are stored as the enum *values* (e.g. 'HOME_TO_UNIVERSITY'), which
    keeps the database readable and the Prisma reference schema identical.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
        **kwargs,
    )


def money_column():
    """Fuel contributions are intentionally NOT platform payments (§7)."""
    from sqlalchemy import Numeric

    return Numeric(10, 2)


PHONE_LEN = 20
NAME_LEN = 120
AREA_LEN = 160
