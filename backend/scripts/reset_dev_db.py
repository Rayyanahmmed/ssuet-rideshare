"""Delete the development SQLite database so the next boot rebuilds it clean.

    python -m scripts.reset_dev_db          # asks for confirmation
    python -m scripts.reset_dev_db --yes    # no prompt (CI, demos)

Only touches a `sqlite:///…` DATABASE_URL. PostgreSQL data is never touched — drop the
database with your normal tooling instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.db.session import sqlite_database_path  # noqa: E402


def main(argv: list[str]) -> int:
    path = sqlite_database_path()
    if path is None:
        print(f"DATABASE_URL is not a SQLite file ({settings.DATABASE_URL}) — nothing to reset.")
        return 1

    targets = [path, Path(f"{path}-wal"), Path(f"{path}-shm")]
    existing = [t for t in targets if t.exists()]
    print(f"Database: {path}")
    if not existing:
        print("Nothing to delete — the next server start will create it fresh.")
        return 0

    if "--yes" not in argv:
        answer = input(f"Delete {len(existing)} file(s) and rebuild on next start? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Cancelled.")
            return 1

    for target in existing:
        target.unlink()
        print(f"  deleted {target.name}")

    print("\nNow start the API (schema is recreated automatically):")
    print("  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000")
    print("Then, optionally, load demo data:")
    print("  python -m scripts.seed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
