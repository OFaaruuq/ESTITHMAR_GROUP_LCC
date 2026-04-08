# Istithmar — Investment management (Flask)

Offline community investment administration: members, agents, contributions, subscriptions, certificates, projects, investments, profit distribution, and reports.

## Layout

This app expects to run from `Admin/istithmar_app` with the Tocly theme assets in `Admin/dist` (sibling folder). Static files are served from `../dist` when present.

## Setup

```bash
cd Admin/istithmar_app
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

## Run (development)

```bash
flask run
# or
python run.py
```

Open `http://127.0.0.1:5000` — default admin can be created on first run (see app seeding).

## Configuration

- Optional: copy `.env.example` to `.env` and set `ISTITHMAR_SECRET_KEY` for production.

### Database

The app uses **PostgreSQL** for staging/development and **Microsoft SQL Server** for production (see `.env.example` and `DEPLOYMENT.md`). Configure `ISTITHMAR_PG_*` or a full `DATABASE_URL`.

- Schema updates: **Flask-Migrate** (`flask db migrate` / `flask db upgrade`).
- Backups: `pg_dump` / `pg_restore` or your host&rsquo;s tools (see Settings for a short reminder).

**Tests** use PostgreSQL only: set `ISTITHMAR_TEST_DATABASE_URL`, or the same `ISTITHMAR_PG_USER` / `ISTITHMAR_PG_PASSWORD` as the app. By default the test DB name is `ISTITHMAR_PG_DATABASE` (same as the app) unless you set `ISTITHMAR_PG_TEST_DATABASE` (e.g. `estithmar_test`) — see `scripts/postgres_create_test_db.sql`.

## Deployment (new server)

Step-by-step install, PostgreSQL, **gunicorn**, **systemd**, **nginx**, TLS, and updates: **[DEPLOYMENT.md](DEPLOYMENT.md)**.

## License

Project-specific; template assets may follow original Tocly license where applicable.
