-- One-time: database for pytest (default name estithmar_test). Run as PostgreSQL superuser.
-- Example: psql -U postgres -f scripts/postgres_create_test_db.sql
CREATE DATABASE estithmar_test OWNER admin_user;
GRANT ALL PRIVILEGES ON DATABASE estithmar_test TO admin_user;
\c estithmar_test
GRANT ALL ON SCHEMA public TO admin_user;
