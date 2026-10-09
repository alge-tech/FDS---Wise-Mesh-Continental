#!/bin/bash
# Runs once, on first database init, as the owner role (POSTGRES_USER).
# Creates the runtime role and the test database. Table grants live in an Alembic
# migration, because the tables don't exist yet when this runs.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE ROLE mesh_app LOGIN PASSWORD '${APP_DB_PASSWORD:-mesh_app}';
  CREATE DATABASE mesh_test OWNER "$POSTGRES_USER";
  GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO mesh_app;
  GRANT CONNECT ON DATABASE mesh_test TO mesh_app;
EOSQL
