#!/usr/bin/env bash
# Nightly backup on the server (cron):  15 3 * * * /opt/replyline/scripts/backup-prod.sh >> /var/log/replyline-backup.log 2>&1
# Dumps both databases, keeps 14 days locally. Copy backups/ off the server too (rclone, restic or
# the provider's snapshot). Restore: see docs/DEPLOYMENT.md "Restore".
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=.env.production
val() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*$//'; }
mkdir -p backups && chmod 700 backups
stamp=$(date -u +%Y%m%d-%H%M%S)
for db in "$(val APP_DB_NAME)" "$(val N8N_DB_NAME)"; do
  docker compose -f infra/compose.prod.yml --env-file "$ENV_FILE" exec -T postgres \
    pg_dump -U "$(val POSTGRES_SUPERUSER)" -Fc "$db" > "backups/$db-$stamp.dump"
  echo "$(date -u +%FT%TZ) backup $db-$stamp.dump $(du -h "backups/$db-$stamp.dump" | cut -f1)"
done
find backups -name '*.dump' -mtime +14 -delete
