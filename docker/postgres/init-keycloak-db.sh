#!/bin/sh
# Creates Keycloak's own database, so its Liquibase migrations and backups stay
# isolated from Manta's schema (and don't show up in `alembic` autogenerate diffs).
#
# Runs only on FIRST initialization of the postgres-data volume. If you have an
# existing dev volume, `docker compose down -v` once to pick this up.
#
# Must stay a .sh, not a .sql: files in /docker-entrypoint-initdb.d/ only get
# environment-variable interpolation if they're shell scripts.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
  CREATE USER ${KC_DB_USERNAME:?} PASSWORD '${KC_DB_PASSWORD:?}';
  CREATE DATABASE ${KC_DB_URL_DATABASE:?} OWNER ${KC_DB_USERNAME:?};
EOSQL
