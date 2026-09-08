#!/bin/sh
set -eu

# Runs automatically via /docker-entrypoint-initdb.d on Postgres's first boot
# only (i.e. when postgres-data is empty) — Keycloak needs its own role and
# database to already exist before it can connect and run its migrations.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE "$KC_DB_USERNAME" WITH LOGIN PASSWORD '$KC_DB_PASSWORD' CREATEDB;
    CREATE DATABASE "$KC_DB_URL_DATABASE" OWNER "$KC_DB_USERNAME";
EOSQL
