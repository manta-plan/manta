#!/bin/sh
set -eu

# Runs automatically via /docker-entrypoint-initdb.d on Postgres's first boot
# only (i.e. when postgres-data is empty) — the Prefect server keeps its state
# in its own database on the shared Postgres instance (instead of the SQLite
# file it defaults to), and needs the role and database to already exist
# before it can connect and run its migrations.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE "$PREFECT_DB_USER" WITH LOGIN PASSWORD '$PREFECT_DB_PASSWORD';
    CREATE DATABASE "$PREFECT_DB_NAME" OWNER "$PREFECT_DB_USER";
EOSQL
