#!/usr/bin/env bash
# Replyline production deploy (run ON THE SERVER, from the repository root):
#   ./scripts/deploy.sh            build + start/update everything, import n8n credentials and workflows
#   ./scripts/deploy.sh --check    only verify the running stack (HTTPS, /internal blocked, health)
# Needs: Docker with the compose plugin, git, python3, curl; a filled-in .env.production.
# Never prints a secret: credentials are piped into n8n, whose output is hidden.
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash on Windows (local rehearsal) would rewrite /tmp paths
cd "$(dirname "$0")/.."

ENV_FILE=.env.production
COMPOSE=(docker compose -f infra/compose.prod.yml --env-file "$ENV_FILE")

[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE (copy .env.production.example and fill it in)."; exit 1; }
if grep -q '=REPLACE_ME' "$ENV_FILE"; then
  echo "Fill in these values in $ENV_FILE first:"; grep -o '^[A-Z_]*=REPLACE_ME' "$ENV_FILE" | cut -d= -f1; exit 1
fi
chmod 600 "$ENV_FILE"
val() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*$//; s/^"//; s/"$//'; }
DOMAIN=$(val DOMAIN)
HTTPS_PORT=$(val HTTPS_PORT); HTTPS_PORT=${HTTPS_PORT:-443}
BASE="https://${DOMAIN}$([ "$HTTPS_PORT" = 443 ] || echo ":$HTTPS_PORT")"
CURL=(curl -fsS --max-time 10)
[ "$(val TLS_MODE)" = internal ] && CURL+=(-k)   # local test with Caddy's own CA

check() {
  echo "--- checks against $BASE"
  "${CURL[@]}" -o /dev/null "$BASE/login" && echo "PASS  HTTPS serves the app"
  code=$(curl -s -o /dev/null -w '%{http_code}' ${CURL[*]:4} "$BASE/api/v1/internal/health" || true)
  [ "$code" = 404 ] && echo "PASS  /api/v1/internal is blocked (404)" || { echo "FAIL  /internal returned $code"; return 1; }
  code=$(curl -s -o /dev/null -w '%{http_code}' ${CURL[*]:4} "$BASE/docs" || true)
  [ "$code" = 404 ] && echo "PASS  API docs hidden (404)" || echo "WARN  /docs returned $code"
  "${CURL[@]}" "$BASE/api/v1/public/forms/$(val DEMO_ORG_SLUG)" -o /dev/null && echo "PASS  backend reachable through the proxy"
  # n8n must be bound to the server's loopback only (reachable just through an SSH tunnel).
  binding=$("${COMPOSE[@]}" port n8n 5678 2>/dev/null || true)
  if [ "${binding%%:*}" = "127.0.0.1" ]; then
    echo "PASS  n8n bound to 127.0.0.1 only ($binding); editor: ssh -L 5678:127.0.0.1:5678 <server>"
  else
    echo "FAIL  n8n published on '$binding'"; return 1
  fi
  if "${COMPOSE[@]}" ps --format '{{.Publishers}}' postgres | grep -q '0.0.0.0'; then
    echo "FAIL  PostgreSQL is published"; return 1
  else
    echo "PASS  PostgreSQL not published"
  fi
}

if [ "${1:-}" = "--check" ]; then check; exit $?; fi

export RELEASE
RELEASE=$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M)
echo "--- building and starting release $RELEASE"
"${COMPOSE[@]}" up -d --build

echo "--- waiting for the backend (migrations run on start)"
for _ in $(seq 1 60); do
  state=$("${COMPOSE[@]}" ps --format '{{.Health}}' backend 2>/dev/null || true)
  [ "$state" = healthy ] && break; sleep 3
done
[ "$state" = healthy ] || { echo "Backend not healthy; see: docker compose -f infra/compose.prod.yml logs backend"; exit 1; }

echo "--- demo organization and n8n service key"
"${COMPOSE[@]}" exec -T backend python -m app.cli seed-demo | grep -v -i 'key' || true

echo "--- n8n credentials (output hidden)"
python3 - "$ENV_FILE" <<'PY' | "${COMPOSE[@]}" exec -T n8n sh -c 'umask 077; cat > /tmp/c.json; n8n import:credentials --input=/tmp/c.json >/tmp/c.log 2>&1; r=$?; rm -f /tmp/c.json /tmp/c.log; exit $r'
import json, sys
env = {}
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k] = v.split(" #")[0].strip().strip('"')
port = int(env.get("SMTP_PORT", "587") or 587)
creds = [
    {"id": "rlCredSvcKey0001", "name": "RL Backend Service Key", "type": "httpHeaderAuth",
     "data": {"name": "X-Service-Key", "value": env["SERVICE_API_KEY"]}},
    {"id": "rlCredWebhook001", "name": "RL Webhook Secret", "type": "httpHeaderAuth",
     "data": {"name": "X-Webhook-Secret", "value": env["N8N_WEBHOOK_SECRET"]}},
    {"id": "rlCredSmtp000001", "name": "RL SMTP", "type": "smtp",
     "data": {"host": env["SMTP_HOST"], "port": port, "user": env.get("SMTP_USER", ""),
              "password": env.get("SMTP_PASSWORD", ""), "secure": port == 465}},
]
if env.get("TELEGRAM_BOT_TOKEN"):
    creds.append({"id": "rlCredTelegram01", "name": "RL Telegram Bot", "type": "telegramApi",
                  "data": {"accessToken": env["TELEGRAM_BOT_TOKEN"]}})
print(json.dumps(creds))
PY
echo "n8n credentials imported"

echo "--- n8n workflows"
tmp=$(mktemp -d ./.deploy-tmp.XXXXXX); trap 'rm -rf "$tmp"' EXIT  # relative: works on Linux and Git Bash
ids=()
use_tg=""; [ -n "$(val TELEGRAM_BOT_TOKEN)" ] && [ -n "$(val TELEGRAM_ALERT_CHAT_ID)" ] && use_tg=1
for f in n8n/workflows/rl-w*.json; do
  # With Telegram configured, W1 comes from the Telegram variant (email stays the fallback).
  [ -n "$use_tg" ] && [ "$(basename "$f")" = rl-w1-lead-intake.json ] && f=n8n/workflows/variants/rl-w1-lead-intake.telegram.json
  sed -e "s#__BACKEND_URL__#$(val BACKEND_URL_FOR_N8N)#g" \
      -e "s#__ALERT_EMAIL_TO__#$(val ALERT_EMAIL_TO)#g" \
      -e "s#__ALERT_EMAIL_FROM__#$(val SMTP_FROM)#g" \
      -e "s#__FRONTEND_URL__#https://${DOMAIN}#g" \
      -e "s#__TELEGRAM_CHAT_ID__#$(val TELEGRAM_ALERT_CHAT_ID)#g" "$f" > "$tmp/wf.json"
  if grep -q '__[A-Z_]*__' "$tmp/wf.json"; then echo "Unfilled placeholder in $f"; exit 1; fi
  "${COMPOSE[@]}" cp "$tmp/wf.json" n8n:/tmp/wf.json
  "${COMPOSE[@]}" exec -T n8n n8n import:workflow --input=/tmp/wf.json >/dev/null 2>&1
  ids+=("$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["id"])' "$tmp/wf.json")")
  echo "imported $(basename "$f")"
done
for id in "${ids[@]}"; do
  "${COMPOSE[@]}" exec -T n8n n8n publish:workflow --id="$id" >/dev/null 2>&1 \
    || "${COMPOSE[@]}" exec -T n8n n8n update:workflow --id="$id" --active=true >/dev/null 2>&1
done
"${COMPOSE[@]}" restart n8n >/dev/null
echo "workflows active: ${#ids[@]}"

sleep 8
check
echo "--- release $RELEASE is live at $BASE"
