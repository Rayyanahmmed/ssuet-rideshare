"""Delete uploaded files that no record references (§16, Phase 10).

An upload becomes an orphan when a member picks a photo and never submits the form,
or replaces one upload with another. This script removes those files once they are
older than the retention window, and reports what it found either way.

Usage
-----
    python -m scripts.sweep_media                    # delete orphans older than MEDIA_ORPHAN_RETENTION_DAYS
    python -m scripts.sweep_media --dry-run          # report only, change nothing
    python -m scripts.sweep_media --days 30          # longer grace window
    python -m scripts.sweep_media --stats            # storage overview, no deletion

Run it from cron when the API process should stay stateless:

    30 3 * * * cd /srv/ssuet-backend && .venv/bin/python -m scripts.sweep_media
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.services.media_service import storage_stats, sweep_orphans

logger = logging.getLogger("ssuet.rideshare.media")


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove orphaned uploaded documents.")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help=f"retention window in days (default {settings.MEDIA_ORPHAN_RETENTION_DAYS})",
    )
    parser.add_argument("--dry-run", action="store_true", help="report only, delete nothing")
    parser.add_argument("--stats", action="store_true", help="print storage statistics and exit")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        if args.stats:
            stats = storage_stats(db)
            print(
                f"files={stats.files} size={_human(stats.bytes)} "
                f"orphans={stats.orphans} orphan_size={_human(stats.orphan_bytes)} "
                f"retention={settings.MEDIA_ORPHAN_RETENTION_DAYS}d"
            )
            return 0

        result = sweep_orphans(db, older_than_days=args.days, dry_run=args.dry_run)
        prefix = "[dry-run] " if args.dry_run else ""
        print(
            f"{prefix}orphans deleted={result.deleted} reclaimed={_human(result.bytes_reclaimed)} "
            f"referenced_kept={result.kept_referenced} within_retention={result.kept_too_new}"
        )
        return 0


if __name__ == "__main__":  # pragma: no cover
    # Configure logging only when run as a program: importing `main` in a test (or in
    # another script) must not mutate the process-wide logging configuration.
    configure_logging()
    sys.exit(main())
