#!/usr/bin/env bash
# One-shot health check for cron/systemd timers (doc 18 §5).
#
#   ./deploy/monitor.sh                                     # human output, exit 0/1
#   BASE_URL=https://… ALERT_WEBHOOK=https://… ./deploy/monitor.sh
#
# Exit codes: 0 healthy · 1 warning · 2 failure. Warnings do not page anyone; failures
# do. Wire it into the timer in deploy/ssuet-monitor.timer, or into any external uptime
# service that just needs one HTTP endpoint: /api/v1/health/ready.

set -Eeuo pipefail

BASE_URL="${BASE_URL:-https://rideshare.ssuet.edu.pk}"
MEDIA_ROOT="${MEDIA_ROOT:-/var/lib/ssuet-rideshare/media}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/ssuet-rideshare}"
MAX_LATENCY_MS="${MAX_LATENCY_MS:-1500}"
MIN_DISK_FREE_PCT="${MIN_DISK_FREE_PCT:-10}"
MIN_CERT_DAYS="${MIN_CERT_DAYS:-14}"
MAX_BACKUP_AGE_HOURS="${MAX_BACKUP_AGE_HOURS:-36}"
CURL_OPTS=(--silent --show-error --max-time 10)

failures=0
warnings=0
lines=()

ok()   { lines+=("OK    $1"); }
warn() { lines+=("WARN  $1"); warnings=$((warnings + 1)); }
fail() { lines+=("FAIL  $1"); failures=$((failures + 1)); }

# ---------------------------------------------------------------- 1. liveness
# `|| true` keeps a connection refusal from aborting the script; the empty result is
# normalised to 000 so the report stays readable.
body=$(curl "${CURL_OPTS[@]}" -o /dev/null -w '%{http_code} %{time_total}' "$BASE_URL/api/v1/health" 2>/dev/null || true)
status=${body%% *}; seconds=${body##* }
status=${status:-000}; seconds=${seconds:-0}
if [[ "$status" == "200" ]]; then
  latency_ms=$(awk -v s="$seconds" 'BEGIN{printf "%d", s*1000}')
  if (( latency_ms > MAX_LATENCY_MS )); then
    warn "liveness slow: ${latency_ms} ms (limit ${MAX_LATENCY_MS})"
  else
    ok "liveness 200 in ${latency_ms} ms"
  fi
else
  fail "liveness returned $status"
fi

# ------------------------------------------------------------- 2. readiness
status=$(curl "${CURL_OPTS[@]}" -o /dev/null -w '%{http_code}' "$BASE_URL/api/v1/health/ready" 2>/dev/null || true)
status=${status:-000}
if [[ "$status" == "200" ]]; then ok "readiness 200 (database reachable)"; else fail "readiness returned $status"; fi

# ----------------------------------------------------------------- 3. TLS
host=${BASE_URL#https://}; host=${host%%/*}
if [[ "$BASE_URL" == https://* ]]; then
  expiry=$(echo | openssl s_client -connect "$host:443" -servername "$host" 2>/dev/null \
            | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2 || true)
  if [[ -n "$expiry" ]]; then
    days=$(( ( $(date -d "$expiry" +%s) - $(date +%s) ) / 86400 ))
    if (( days < MIN_CERT_DAYS )); then fail "certificate expires in ${days} day(s)"; else ok "certificate valid for ${days} day(s)"; fi
  else
    warn "could not read the certificate"
  fi
fi

# ---------------------------------------------------------------- 4. disk
if [[ -d "$MEDIA_ROOT" ]]; then
  free_pct=$(df --output=pcent "$MEDIA_ROOT" | tail -1 | tr -dc '0-9')
  free_pct=$(( 100 - free_pct ))
  if (( free_pct < MIN_DISK_FREE_PCT )); then fail "media volume only ${free_pct}% free"; else ok "media volume ${free_pct}% free"; fi
fi

# -------------------------------------------------------------- 5. backups
if [[ -d "$BACKUP_DIR" ]]; then
  newest=$(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %f\n' 2>/dev/null | sort -n | tail -1 | awk '{print $1}')
  if [[ -n "$newest" ]]; then
    age_h=$(( ( $(date +%s) - ${newest%.*} ) / 3600 ))
    if (( age_h > MAX_BACKUP_AGE_HOURS )); then fail "newest backup is ${age_h} h old"; else ok "newest backup is ${age_h} h old"; fi
  else
    warn "no backups found in $BACKUP_DIR"
  fi
fi

# ------------------------------------------------------------ 6. report out
exit_code=0
(( failures > 0 )) && exit_code=2
(( exit_code == 0 && warnings > 0 )) && exit_code=1

printf '%s\n' "${lines[@]}"
summary="SSUET RideShare monitor: ${failures} failure(s), ${warnings} warning(s) on ${BASE_URL}"
echo "$summary"

if [[ "$exit_code" -ne 0 && -n "${ALERT_WEBHOOK:-}" ]]; then
  curl "${CURL_OPTS[@]}" -X POST -H 'Content-Type: application/json' \
       -d "$(printf '{"text":"%s\\n%s"}' "$summary" "$(printf '%s\n' "${lines[@]}" | tr '\n' ';')")" \
       "$ALERT_WEBHOOK" >/dev/null || echo "(alert webhook failed)"
fi

exit "$exit_code"
