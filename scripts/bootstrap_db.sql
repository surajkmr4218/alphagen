-- One-time bootstrap for a fresh database, run as the `app` superuser:
--
--   docker compose exec -T db psql -U app -d alphagen \
--     -v pw="$(grep '^APP_DB_PASSWORD=' .env | cut -d= -f2)" < scripts/bootstrap_db.sql
--
-- Superuser is needed only here (CREATE EXTENSION). The app itself connects as
-- `alphagen_app`, a NOSUPERUSER role — superusers bypass row-level security, so the
-- tenant-isolation policies only enforce for a non-superuser. Idempotent: re-running
-- updates the role password to the current APP_DB_PASSWORD.

CREATE EXTENSION IF NOT EXISTS vector;

SELECT set_config('bootstrap.pw', :'pw', false);

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'alphagen_app') THEN
    EXECUTE format(
      'CREATE ROLE alphagen_app LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE',
      current_setting('bootstrap.pw')
    );
  ELSE
    EXECUTE format(
      'ALTER ROLE alphagen_app PASSWORD %L',
      current_setting('bootstrap.pw')
    );
  END IF;
END $$;

GRANT CONNECT ON DATABASE alphagen TO alphagen_app;
-- CREATE so alembic migrations (which run as alphagen_app) can add tables.
GRANT USAGE, CREATE ON SCHEMA public TO alphagen_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO alphagen_app;
-- Serial primary keys need sequence USAGE on insert.
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO alphagen_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO alphagen_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO alphagen_app;
