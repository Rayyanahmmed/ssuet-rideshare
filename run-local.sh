#!/usr/bin/env bash
# Runs the whole project locally in production mode, from this folder.
#   API     http://127.0.0.1:8100/api/v1   (uvicorn, ENVIRONMENT=production)
#   Web app http://localhost:8181          (built with EXPO_PUBLIC_API_URL -> API above)
#   Admin   http://localhost:8190          (built with VITE_API_BASE_URL -> API above)
# Needs PostgreSQL on 127.0.0.1:5432 with database "ssuet_app" (see documentation/28, section 3).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
API_PORT=8100 WEB_PORT=8181 ADMIN_PORT=8190
DB_URL="${DATABASE_URL:-postgresql+psycopg://ssuet:ssuet_test_pw@127.0.0.1:5432/ssuet_app}"
JWT_FILE="$ROOT/.local-jwt-secret"
[ -f "$JWT_FILE" ] || python3 -c "import secrets;print(secrets.token_urlsafe(48))" > "$JWT_FILE"

API_URL="http://127.0.0.1:$API_PORT/api/v1"
if [ "${1:-}" = "--build" ] || [ ! -d "$ROOT/mobile/dist" ]; then
  (cd "$ROOT/mobile" && EXPO_PUBLIC_API_URL="$API_URL" EXPO_PUBLIC_ALLOW_SERVER_OVERRIDE=0 npx expo export -p web -c)
  (cd "$ROOT/admin-dashboard" && VITE_API_BASE_URL="$API_URL" npm run build)
fi

(cd "$ROOT/backend" && exec env ENVIRONMENT=production DEBUG=false LOG_LEVEL=INFO AUTO_CREATE_TABLES=false \
  DATABASE_URL="$DB_URL" JWT_SECRET_KEY="$(cat "$JWT_FILE")" \
  ADMIN_BOOTSTRAP_ENABLED=true ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD='Admin@SSUET2026' \
  ADMIN_WEB_URL="http://localhost:$ADMIN_PORT" \
  CORS_ORIGINS="http://localhost:$WEB_PORT,http://127.0.0.1:$WEB_PORT,http://localhost:$ADMIN_PORT,http://127.0.0.1:$ADMIN_PORT" \
  MAP_PROVIDER=osm APP_DEEP_LINK_BASE=ssuetrideshare:// \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$API_PORT") &
python3 "$ROOT/tools/serve_spa.py" "$ROOT/mobile/dist" "$WEB_PORT" &
python3 "$ROOT/tools/serve_spa.py" "$ROOT/admin-dashboard/dist" "$ADMIN_PORT" &
echo "Running: web http://localhost:$WEB_PORT  admin http://localhost:$ADMIN_PORT  api $API_URL"
wait
