"""Structured, dependency-free logging setup (§19)."""

from __future__ import annotations

import logging
import re
import sys

from app.core.config import settings


class SensitiveDataFilter(logging.Filter):
    """Defensive redaction so secrets never reach log sinks."""

    # matches: password=..., "token": "...", api_key: '...', Bearer xxx
    PATTERN = re.compile(
        r"(password|passwd|token|secret|api[_-]?key|authorization)"
        r"(\s*[=:]\s*|\s+bearer\s+)\S+",
        re.IGNORECASE,
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self.PATTERN.sub(lambda m: f"{m.group(1)}=***", message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )
    handler.addFilter(SensitiveDataFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL)

    # SQL is only logged when DB_ECHO is explicitly enabled.
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DB_ECHO else logging.WARNING
    )
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)


logger = logging.getLogger("ssuet.rideshare")
