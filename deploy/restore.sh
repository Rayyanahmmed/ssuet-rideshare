#!/usr/bin/env bash
# Restore a backup produced by backup.sh (doc 17 §6).
#
#   sudo -u ssuet ./restore.sh /var/backups/ssuet-rideshare/20261106T031500Z
#
# Refuses to run against a live service: stop the API first.
#   sudo systemctl stop ssuet-api
#   sudo -u ssuet ./restore.sh <dir>
#   sudo systemctl start ssuet-api
#
# Restores into the targets described by the environment file, so the check is
# deliberate: this script overwrites the database and the media directory.

set -Eeuo pipefail

SOURCE="${1:?usage: restore.sh <backup-directory>}"
ENV_FILE="${ENV_FILE:-/etc/ssuet-rideshare/api.env}"

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


[[ -d "$SOURCE" ]] || { echo "not a directory: $SOURCE" >&2; exit 1; }
[[ -r "$SOURCE/MANIFEST" ]] || { echo "missing MANIFEST — is this a backup directory?" >&2; exit 1; }

if systemctl is-active --quiet ssuet-api 2>/dev/null; then
  echo "ssuet-api is running. Stop it first: sudo systemctl stop ssuet-api" >&2
  exit 1
fi

echo "About to restore:"; cat "$SOURCE/MANIFEST"; echo
read -r -p "Type RESTORE to continue: " confirm
[[ "$confirm" == "RESTORE" ]] || { echo "aborted"; exit 1; }

( cd "$SOURCE" && sha256sum -c SHA256SUMS )

DATABASE_URL="$(read_env DATABASE_URL "$ENV_FILE")"
MEDIA_ROOT="$(read_env MEDIA_ROOT "$ENV_FILE")"
ENVIRONMENT="$(read_env ENVIRONMENT "$ENV_FILE")"
: "${DATABASE_URL:?DATABASE_URL must be set in $ENV_FILE}"
: "${MEDIA_ROOT:?MEDIA_ROOT must be set in $ENV_FILE}"

# ---------- database ----------
if [[ -f "$SOURCE/database.dump" ]]; then
  PGUSER="$(python3 -c 'import os,urllib.parse as u;print(u.urlparse(os.environ["DATABASE_URL"].replace("+psycopg","")).username or "")')"
  PGPASSWORD="$(python3 -c 'import os,urllib.parse as u;print(u.urlparse(os.environ["DATABASE_URL"].replace("+psycopg","")).password or "")')"
  PGHOST="$(python3 -c 'import os,urllib.parse as u;print(u.urlparse(os.environ["DATABASE_URL"].replace("+psycopg","")).hostname or "localhost")')"
  PGDATABASE="$(python3 -c 'import os,urllib.parse as u;print((u.urlparse(os.environ["DATABASE_URL"].replace("+psycopg","")).path or "/ssuet").lstrip("/"))')"
  export PGPASSWORD
  pg_restore --host "$PGHOST" --username "$PGUSER" --dbname "$PGDATABASE" \
             --clean --if-exists --no-owner --no-privileges "$SOURCE/database.dump"
  echo "[restore] database restored"
elif [[ -f "$SOURCE/database.sqlite3" ]]; then
  SQLITE_PATH="${DATABASE_URL#sqlite+pysqlite:///}"
  cp "$SOURCE/database.sqlite3" "$SQLITE_PATH"
  echo "[restore] sqlite database restored to $SQLITE_PATH"
fi

# ---------- documents ----------
if [[ -f "$SOURCE/media.tar.gz" ]]; then
  mkdir -p "$MEDIA_ROOT"
  find "$MEDIA_ROOT" -mindepth 1 -delete
  tar -C "$MEDIA_ROOT" -xzf "$SOURCE/media.tar.gz"
  echo "[restore] media restored ($(find "$MEDIA_ROOT" -type f | wc -l) files)"
fi

echo "[restore] done — start the service and run deploy/smoke.sh"
