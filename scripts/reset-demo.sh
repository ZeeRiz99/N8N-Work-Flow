#!/usr/bin/env bash
# Public demo only: replace the demo organization's sample leads with a fresh fictional set.
# Real leads (not flagged as sample data) are never touched. Cron for a nightly reset:
#   0 4 * * * /opt/replyline/scripts/reset-demo.sh >> /var/log/replyline-demo.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
C=(docker compose -f infra/compose.prod.yml --env-file .env.production exec -T backend)
"${C[@]}" python -m app.cli sample-data --org "${DEMO_ORG:-harbor-web}" --clear
"${C[@]}" python -m app.cli sample-data --org "${DEMO_ORG:-harbor-web}" --count 150 --days 60
