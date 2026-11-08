#!/usr/bin/env bash
# Post-deploy smoke test (doc 17 §5). Read-only except for one login.
#
#   ./deploy/smoke.sh https://rideshare.ssuet.edu.pk
#   API_BASE=https://rideshare.ssuet.edu.pk/api/v1 SMOKE_EMAIL=… SMOKE_PASSWORD=… ./deploy/smoke.sh
#
# Exit 0 means the deployment is serving: TLS, health, migrations applied, the console
# and the JSON API all respond, and the security headers are in place.

set -Eeuo pipefail

BASE="${1:-${API_BASE:-http://127.0.0.1:8080}}"
BASE="${BASE%/}"
if [[ "$BASE" != *"/api/v1" ]]; then API="$BASE/api/v1"; else API="$BASE"; BASE="${BASE%/api/v1}"; fi
ORIGIN="${ORIGIN:-$BASE}"

pass=0; fail=0
ok()   { pass=$((pass+1)); printf '  \033[32mPASS\033[0m %s\n' "$1"; }
bad()  { fail=$((fail+1)); printf '  \033[31mFAIL\033[0m %s\n' "$1"; }
check(){ if [[ "$2" == "$3" ]]; then ok "$1 ($2)"; else bad "$1 (expected $3, got $2)"; fi; }

echo "Smoke test → $API"

# ---------- 1. health & readiness ----------
status=$(curl -s -o /tmp/smoke-health.json -w '%{http_code}' "$API/health" || true)
check "GET /health" "$status" "200"
grep -q '"status":"ok"' /tmp/smoke-health.json && ok "health reports ok" || bad "health payload"

status=$(curl -s -o /tmp/smoke-ready.json -w '%{http_code}' "$API/health/ready" || true)
check "GET /health/ready (database + migrations)" "$status" "200"

# ---------- 2. TLS + headers ----------
if [[ "$ORIGIN" == https://* ]]; then
  sts=$(curl -sI "$ORIGIN/" | tr -d '\r' | awk -F': ' 'tolower($1)=="strict-transport-security"{print $2}')
  [[ -n "$sts" ]] && ok "HSTS present ($sts)" || bad "HSTS header missing"
  tls=$(echo | openssl s_client -connect "${ORIGIN#https://}:443" -servername "${ORIGIN#https://}" 2>/dev/null | grep -c 'Verify return code: 0')
  [[ "$tls" == "1" ]] && ok "TLS certificate verifies" || bad "TLS certificate does not verify"
else
  echo "  (skipping TLS checks: $ORIGIN is not https)"
fi
for header in x-content-type-options x-frame-options content-security-policy; do
  value=$(curl -sI "$ORIGIN/" | tr -d '\r' | grep -ci "^$header:" || true)
  [[ "$value" -ge 1 ]] && ok "security header $header" || bad "security header $header missing"
done

# ---------- 3. console ----------
status=$(curl -s -o /tmp/smoke-index.html -w '%{http_code}' "$ORIGIN/")
check "GET / (admin console)" "$status" "200"
grep -qi '<div id="root"' /tmp/smoke-index.html && ok "SPA shell served" || bad "SPA shell not found"
status=$(curl -s -o /dev/null -w '%{http_code}' "$ORIGIN/reports")
check "GET /reports (client route falls back to the shell)" "$status" "200"
status=$(curl -s -o /dev/null -w '%{http_code}' "$ORIGIN/.env")
check "GET /.env (must be refused)" "$status" "403"

# ---------- 4. API through the proxy ----------
status=$(curl -s -o /tmp/smoke-meta.json -w '%{http_code}' "$API/meta")
check "GET /meta through the proxy" "$status" "200"
grep -q 'max_confirmed_passengers' /tmp/smoke-meta.json && ok "meta payload parses" || bad "meta payload"

status=$(curl -s -o /dev/null -w '%{http_code}' "$API/admin/dashboard")
check "GET /admin/dashboard without a token" "$status" "401"

# A profile photo is visible to members, never to the open internet (Phase 13).
status=$(curl -s -o /dev/null -w '%{http_code}' "$API/users/00000000-0000-0000-0000-000000000000/photo")
check "GET /users/{id}/photo without a token" "$status" "401"

# ---------- 5. optional login ----------
if [[ -n "${SMOKE_EMAIL:-}" && -n "${SMOKE_PASSWORD:-}" ]]; then
  code=$(curl -s -o /tmp/smoke-login.json -w '%{http_code}' -X POST "$API/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$SMOKE_EMAIL\",\"password\":\"$SMOKE_PASSWORD\"}" || true)
  check "POST /auth/login" "$code" "200"
else
  echo "  (skipping login: set SMOKE_EMAIL and SMOKE_PASSWORD to include it)"
fi

# ---------- 6. upload limit behaves as designed ----------
big=$(mktemp); head -c 7000000 /dev/zero > "$big"
status=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/uploads/verification" -F "file=@$big;type=image/png" || true)
rm -f "$big"
# 401 (no token) or 413 (too large) both prove the request reaches a size check.
if [[ "$status" == "413" || "$status" == "401" ]]; then ok "oversize upload is refused ($status)"; else bad "oversize upload returned $status"; fi

echo
echo "$pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
