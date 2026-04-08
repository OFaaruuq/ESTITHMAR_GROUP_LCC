#!/usr/bin/env bash
# Align local PostgreSQL (not Docker) with admin_user / estithmar_db / password Isth@12345.
# Uses peer auth: run on Ubuntu/WSL as a user in group postgres, or adjust to use -h 127.0.0.1 -U postgres with PG password.
set -euo pipefail
sudo -u postgres psql -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
  CREATE ROLE admin_user LOGIN PASSWORD 'Isth@12345';
EXCEPTION
  WHEN duplicate_object THEN
    ALTER ROLE admin_user WITH PASSWORD 'Isth@12345';
END
$$;
SQL
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='estithmar_db'" | grep -q 1; then
  sudo -u postgres createdb -O admin_user estithmar_db
fi
sudo -u postgres psql -v ON_ERROR_STOP=1 -d estithmar_db <<'SQL'
GRANT ALL ON SCHEMA public TO admin_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO admin_user;
SQL
echo "OK: admin_user can connect to database estithmar_db with the configured password."
