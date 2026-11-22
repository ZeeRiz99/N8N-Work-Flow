#!/bin/bash
# Runs once, on the first start of an empty PostgreSQL volume.
# Creates the app and n8n databases, each owned by its own role, and blocks cross-access.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
	CREATE ROLE ${APP_DB_USER} LOGIN PASSWORD '${APP_DB_PASSWORD}';
	CREATE DATABASE ${APP_DB_NAME} OWNER ${APP_DB_USER};
	REVOKE ALL ON DATABASE ${APP_DB_NAME} FROM PUBLIC;

	CREATE ROLE ${N8N_DB_USER} LOGIN PASSWORD '${N8N_DB_PASSWORD}';
	CREATE DATABASE ${N8N_DB_NAME} OWNER ${N8N_DB_USER};
	REVOKE ALL ON DATABASE ${N8N_DB_NAME} FROM PUBLIC;

	-- Integration tests use their own database, never the development data.
	CREATE DATABASE ${APP_DB_NAME}_test OWNER ${APP_DB_USER};
	REVOKE ALL ON DATABASE ${APP_DB_NAME}_test FROM PUBLIC;
EOSQL

for db in "$APP_DB_NAME" "${APP_DB_NAME}_test"; do
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<-EOSQL
	CREATE EXTENSION IF NOT EXISTS citext;
	CREATE EXTENSION IF NOT EXISTS pg_trgm;
	REVOKE CREATE ON SCHEMA public FROM PUBLIC;
	GRANT ALL ON SCHEMA public TO ${APP_DB_USER};
EOSQL
done
