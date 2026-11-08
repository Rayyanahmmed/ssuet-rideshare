#!/usr/bin/env bash
# Back up the database **and** the uploaded documents (§16, doc 17 §6).
#
#   sudo -u ssuet /srv/ssuet-rideshare/deploy/backup.sh
#   sudo -u ssuet /srv/ssuet-rideshare/deploy/backup.sh --keep 30
#
# Cron (03:15 daily), as the service user:
#   15 3 * * * /srv/ssuet-rideshare/deploy/backup.sh >> /var/log/ssuet-backup.log 2>&1
#
# A database dump alone is not a backup: verification documents live on disk, and a
# restore without them leaves rows that point at files nobody can open.

set -Eeuo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/ssuet-rideshare}"
KEEP="${KEEP:-14}"

read_env() {  # read_env KEY FILE — parse, never execute, the environment file
  python3 - "$1" "$2" <<'PYEOF'
import pathlib, sys
key, path = sys.argv[1], sys.argv[2]
for line in pathlib.Path(path).read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    name, value = line.split("=", 1)
    if name.strip() == key:
        print(value.strip().strip('"').strip("'"))
        break
PYEOF
}

ENV_FILE="${ENV_FILE:-/etc/ssuet-rideshare/api.env}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep) KEEP="$2"; shift 2 ;;
    --dir)  BACKUP_DIR="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -r "$ENV_FILE" ]] || { echo "cannot read $ENV_FILE" >&2; exit 1; }
DATABASE_URL="$(read_env DATABASE_URL "$ENV_FILE")"
MEDIA_ROOT="$(read_env MEDIA_ROOT "$ENV_FILE")"
ENVIRONMENT="$(read_env ENVIRONMENT "$ENV_FILE")"
: "${DATABASE_URL:?DATABASE_URL must be set in $ENV_FILE}"
: "${MEDIA_ROOT:?MEDIA_ROOT must be set in $ENV_FILE}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="$BACKUP_DIR/$STAMP"
mkdir -p "$TARGET"

echo "[backup] $STAMP → $TARGET"

# ---------- database ----------
if [[ "$DATABASE_URL" == postgresql* ]]; then
  # Translate SQLAlchemy URL → libpq arguments without embedding credentials in argv.
  PGUSER="$(python3 - <<'PY'
import os, urllib.parse as u
print(u.urlparse(os.environ["DATABASE_URL"].replace("+psycopg", "")).username or "")
PY
)"
  PGPASSWORD="$(python3 - <<'PY'
import os, urllib.parse as u
print(u.urlparse(os.environ["DATABASE_URL"].replace("+psycopg", "")).password or "")
PY
)"
  PGHOST="$(python3 - <<'PY'
import os, urllib.parse as u
print(u.urlparse(os.environ["DATABASE_URL"].replace("+psycopg", "")).hostname or "localhost")
PY
)"
  PGDATABASE="$(python3 - <<'PY'
import os, urllib.parse as u
print((u.urlparse(os.environ["DATABASE_URL"].replace("+psycopg", "")).path or "/ssuet").lstrip("/"))
PY
)"
  export PGPASSWORD
  pg_dump --host "$PGHOST" --username "$PGUSER" --dbname "$PGDATABASE" \
          --format custom --no-owner --no-privileges > "$TARGET/database.dump"
  echo "[backup] database.dump $(du -h "$TARGET/database.dump" | cut -f1)"
else
  # SQLite (development / staging): copy the file consistently.
  SQLITE_PATH="${DATABASE_URL#sqlite+pysqlite:///}"
  sqlite3 "$SQLITE_PATH" ".backup '$TARGET/database.sqlite3'"
  echo "[backup] database.sqlite3 $(du -h "$TARGET/database.sqlite3" | cut -f1)"
fi

# ---------- uploaded documents ----------
if [[ -d "$MEDIA_ROOT" ]]; then
  tar -C "$MEDIA_ROOT" -czf "$TARGET/media.tar.gz" .
  echo "[backup] media.tar.gz $(du -h "$TARGET/media.tar.gz" | cut -f1) ($(find "$MEDIA_ROOT" -type f | wc -l) files)"
else
  echo "[backup] WARNING: MEDIA_ROOT=$MEDIA_ROOT does not exist — no documents backed up" >&2
fi

# ---------- manifest + integrity ----------
{
  echo "created_at=$STAMP"
  echo "environment=${ENVIRONMENT:-unknown}"
  echo "database_url_scheme=${DATABASE_URL%%:*}"
  echo "media_root=$MEDIA_ROOT"
} > "$TARGET/MANIFEST"
( cd "$TARGET" && sha256sum ./* > SHA256SUMS )

# ---------- retention ----------
if [[ "$KEEP" -gt 0 ]]; then
  find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' \
    | sort -r | tail -n +$((KEEP + 1)) \
    | while read -r old; do rm -rf "${BACKUP_DIR:?}/$old"; echo "[backup] pruned $old"; done
fi

echo "[backup] done"
