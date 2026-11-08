"""Process-level runtime facts used by `/admin/health` (doc 18).

Deliberately tiny and in-memory: uptime, and when the housekeeping loop last ran. On a
deployment where the scheduler is disabled (`MAINTENANCE_INTERVAL_MINUTES=0`) the
maintenance fields stay `None` — the cron entries own that work there, and the panel
says so rather than pretending.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

STARTED_AT = time.time()
_STARTED_DT = datetime.now(timezone.utc)


@dataclass
class MaintenanceRun:
    finished_at: datetime
    result: dict[str, Any] = field(default_factory=dict)


_last_maintenance: MaintenanceRun | None = None


def record_maintenance(result: dict[str, Any]) -> None:
    global _last_maintenance
    _last_maintenance = MaintenanceRun(finished_at=datetime.now(timezone.utc), result=result)


def last_maintenance() -> MaintenanceRun | None:
    return _last_maintenance


def uptime_seconds() -> float:
    return round(time.time() - STARTED_AT, 1)


def process_info() -> dict[str, Any]:
    """Enough to tell *which* worker answered, without leaking anything sensitive."""
    return {
        "pid": os.getpid(),
        "started_at": _STARTED_DT.isoformat(),
        "uptime_seconds": uptime_seconds(),
    }
