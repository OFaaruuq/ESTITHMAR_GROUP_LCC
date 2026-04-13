# Estithmar — Investment management (Flask)

Offline community investment administration: members, agents, contributions, subscriptions, certificates, projects, investments, profit distribution, and reports.

## Layout

Run from the **project root** (the folder that contains `app.py`, `run.py`, and `venv/`). Static assets are served from `../dist` when present.

## Setup

```bash
cd D:\ESTITHMAR_GROUP_LCC
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Run on Windows

### Prerequisites

1. **Python 3.11+** (64-bit recommended).
2. **Microsoft ODBC Driver for SQL Server** (17 or 18) — required for `pyodbc`. Install from [Microsoft’s ODBC download page](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server).
3. **Database**: install **SQL Server** (Express or full) locally, **or** start SQL Server in Docker with `docker compose up -d` (see `docker-compose.yml`). Ensure `DATABASE_URL` / `DB_*` in `.env` match your instance (host `127.0.0.1`, port `1433` when connecting from the host).

### Configure

Copy `.env.example` to `.env` and set at least `ESTITHMAR_SECRET_KEY`, `ESTITHMAR_ENV`, and your database URL or `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD`. For SQL Server in development, `DATABASE_URL` can look like:

`mssql+pyodbc://USER:PASSWORD@127.0.0.1:1433/estithmar_db?driver=ODBC+Driver+17+for+SQL+Server`

(Use **ODBC Driver 18** in the URL if that is what you installed; add `&TrustServerCertificate=yes` for local dev if needed.)

Apply the schema (from project root, venv activated):

```powershell
flask db upgrade
```

### Development (auto-reload, single machine)

```powershell
.\run-dev.ps1
```

Or: `flask run` — open `http://127.0.0.1:5000`.

### Production-style on Windows (Waitress, LAN access)

`python run.py` serves with **Waitress** on `0.0.0.0:5000` by default, so other PCs on the same network can use `http://<this-pc-ip>:5000`. If Windows Firewall prompts, allow access for Python on private networks, or open TCP port **5000** manually.

Optional environment variables: `WAITRESS_HOST`, `WAITRESS_PORT`, or `PORT`.

## Run (quick reference)

```bash
flask run
# or (Waitress, binds all interfaces)
python run.py
```

Open `http://127.0.0.1:5000` — default admin can be created on first run (see app seeding).

## Configuration

- Optional: copy `.env.example` to `.env` and set `ESTITHMAR_SECRET_KEY` for production.

### Database

**Development** can use **PostgreSQL** or **Microsoft SQL Server** (see `.env.example`). **Staging** expects PostgreSQL; **production** expects SQL Server. Configure `DATABASE_URL` or the `DB_*` / `ESTITHMAR_PG_*` variables as documented in `.env.example`.

- Schema updates: **Flask-Migrate** (`flask db migrate` / `flask db upgrade`).
- SQL Server in Docker: see comments in `docker-compose.yml` for creating the database the first time.

**Tests** use PostgreSQL only: set `ESTITHMAR_TEST_DATABASE_URL`, or the same `ESTITHMAR_PG_USER` / `ESTITHMAR_PG_PASSWORD` as the app. By default the test DB name is `ESTITHMAR_PG_DATABASE` (same as the app) unless you set `ESTITHMAR_PG_TEST_DATABASE` (e.g. `estithmar_test`) — see `scripts/postgres_create_test_db.sql`.

## Deployment (Linux server)

Step-by-step install, PostgreSQL, **gunicorn**, **systemd**, **nginx**, TLS, and updates: **[DEPLOYMENT.md](DEPLOYMENT.md)**.

## License

Project-specific; template assets may follow original Tocly license where applicable.
