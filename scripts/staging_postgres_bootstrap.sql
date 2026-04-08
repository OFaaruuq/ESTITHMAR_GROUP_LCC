-- Run as a PostgreSQL superuser (e.g. postgres) on a staging server when NOT using Docker auto-setup.
-- Example: psql -U postgres -f scripts/staging_postgres_bootstrap.sql

CREATE USER admin_user WITH PASSWORD 'Isth@12345';
CREATE DATABASE estithmar_db OWNER admin_user;
GRANT ALL PRIVILEGES ON DATABASE estithmar_db TO admin_user;

\c estithmar_db
GRANT ALL ON SCHEMA public TO admin_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO admin_user;
