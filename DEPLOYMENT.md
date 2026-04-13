# Installing and deploying Estithmar on a new server

This guide assumes a **Linux** production host (Ubuntu 22.04/24.04 or similar). Adapt paths and package names for your distribution.

## 1. What the app needs

| Requirement | Notes |
|-------------|--------|
| **Python** | 3.10+ recommended |
| **Theme assets** | Tocly `dist/` folder next to `estithmar_app` (see layout below) |
| **Database** | **PostgreSQL** on staging; **Microsoft SQL Server** on production (see §6). Local dev uses PostgreSQL (e.g. Docker; see `docker-compose.yml`). |
| **Reverse proxy** | **nginx** (or Caddy) in front of the WSGI process, TLS termination |
| **Process manager** | **systemd** + **gunicorn** (included in `requirements.txt`) |

### Repository layout on the server

The app resolves static files from `../dist` (relative to `estithmar_app`). After clone or upload you should have:

```text
/opt/estithmar/   (example root)
  dist/           ← Tocly build output (must contain dist/assets/...)
  estithmar_app/  ← this repository (app.py, run.py, estithmar/, templates/, ...)
```

If your clone only contains `estithmar_app/`, copy the **Admin/dist** theme folder from your template package so it sits as a **sibling** of `estithmar_app`, or adjust deployment to match `resolve_static_folder()` in `estithmar/config.py`.

## 2. System packages (Ubuntu example)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx postgresql postgresql-contrib git
```

## 3. Database (PostgreSQL)

Create a database and user (replace passwords and names):

```bash
sudo -u postgres psql <<'SQL'
CREATE USER estithmar WITH PASSWORD 'your-secure-password';
CREATE DATABASE estithmar OWNER estithmar;
GRANT ALL PRIVILEGES ON DATABASE estithmar TO estithmar;
SQL
```

For PostgreSQL 15+ you may need schema privileges on the database:

```bash
sudo -u postgres psql -d estithmar -c 'GRANT ALL ON SCHEMA public TO estithmar;'
```

Connection URL for the app (SQLAlchemy):

```text
postgresql+psycopg2://estithmar:your-secure-password@127.0.0.1:5432/estithmar
```

## 4. Application user and code

```bash
sudo useradd -r -m -d /opt/estithmar -s /bin/bash estithmar || true
sudo mkdir -p /opt/estithmar
sudo chown estithmar:estithmar /opt/estithmar
```

As `estithmar` (or use `sudo -u estithmar bash`):

```bash
cd /opt/estithmar
git clone https://github.com/OFaaruuq/estithmar-investment-platform.git estithmar_app
cd estithmar_app
```

Ensure `../dist` exists with `assets/` inside (copy from your Tocly **Admin/dist** bundle if missing).

## 5. Python virtualenv and dependencies

```bash
cd /opt/estithmar/estithmar_app
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 6. Environment configuration

```bash
cp .env.example .env
chmod 600 .env
nano .env   # or vi
```

Set at minimum:

| Variable | Required | Description |
|----------|----------|-------------|
| `ESTITHMAR_SECRET_KEY` | **Yes** (production) | Long random string; used for sessions and CSRF. Generate e.g. `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ESTITHMAR_ENV` | **Yes** | `staging` (PostgreSQL), `production` (SQL Server), or `development`. |
| `ESTITHMAR_DATABASE_URL` or `DATABASE_URL` | **Yes** (or env-specific URL) | Primary DB URI. Alternatively set `ESTITHMAR_STAGING_DATABASE_URL`, `ESTITHMAR_PRODUCTION_DATABASE_URL`, or `ESTITHMAR_DEVELOPMENT_DATABASE_URL` to match `ESTITHMAR_ENV`. |
| `FLASK_ENV` | Optional | Omit or `production` — do **not** set `development` on a public server. |

Example `.env` for **staging** (PostgreSQL):

```env
ESTITHMAR_ENV=staging
ESTITHMAR_SECRET_KEY=<paste-generated-hex>
ESTITHMAR_STAGING_DATABASE_URL=postgresql+psycopg2://estithmar:your-secure-password@127.0.0.1:5432/estithmar
```

Example for **production** (SQL Server; install `pyodbc` and the Microsoft ODBC driver on the host):

```env
ESTITHMAR_ENV=production
ESTITHMAR_SECRET_KEY=<paste-generated-hex>
ESTITHMAR_PRODUCTION_DATABASE_URL=mssql+pyodbc://estithmar:your-secure-password@127.0.0.1:1433/estithmar?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes
```

**Note:** `postgres://` URLs (e.g. from Heroku) are normalized automatically; `postgresql+psycopg2://` is explicit and recommended for self-hosted Postgres.

## 7. First start and schema

The app uses **Flask-Migrate** (Alembic). With PostgreSQL configured in `.env` and venv activated:

```bash
source venv/bin/activate
pip install -r requirements.txt
flask db upgrade
python -c "from estithmar import create_app; create_app()"
```

The repository includes an initial migration under `migrations/versions/`. `flask db upgrade` applies it; on startup the app also runs `upgrade()` when `migrations/env.py` exists (and falls back to `create_all()` only if upgrade fails).

After you change SQLAlchemy models, generate and apply migrations:

```bash
flask db migrate -m "describe change"
flask db upgrade
```

**Do not run `flask db init`** on this project: the `migrations/` directory is already in the repository. That command is only for brand-new apps. If you see *Directory migrations already exists and is not empty*, skip `init` and use `migrate` / `upgrade` only.

For PostgreSQL or SQL Server, use your platform backups (`pg_dump`, native SQL Server backups, or your cloud provider).

Complete the first-login / seed flow in the browser after gunicorn is running (see below).

## 8. Run with Gunicorn (production)

Working directory **must** be the folder that contains `app.py` and `run.py`.

```bash
cd /opt/estithmar/estithmar_app
source venv/bin/activate
gunicorn -w 4 -b 127.0.0.1:8000 --timeout 120 'app:app'
```

- `-w 4`: worker processes (often `2 * CPUs + 1` as a starting point).
- `-b 127.0.0.1:8000`: listen only on localhost; nginx talks to this port.

## 9. systemd service

Create `/etc/systemd/system/estithmar.service`:

```ini
[Unit]
Description=Estithmar Flask app
After=network.target postgresql.service

[Service]
User=estithmar
Group=estithmar
WorkingDirectory=/opt/estithmar/estithmar_app
Environment="PATH=/opt/estithmar/estithmar_app/venv/bin"
ExecStart=/opt/estithmar/estithmar_app/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 --timeout 120 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable estithmar
sudo systemctl start estithmar
sudo systemctl status estithmar
```

## 10. nginx reverse proxy

Example `/etc/nginx/sites-available/estithmar`:

```nginx
server {
    listen 80;
    server_name your.domain.com;

    client_max_body_size 25M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable the site and reload:

```bash
sudo ln -sf /etc/nginx/sites-available/estithmar /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## 11. TLS (HTTPS)

Use **Certbot** (Let’s Encrypt) or your host’s certificate manager. After HTTP works:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your.domain.com
```

## 12. Firewall

Allow SSH and HTTP/HTTPS only as needed:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

## 13. Deploying updates

```bash
cd /opt/estithmar/estithmar_app
sudo -u estithmar git pull
sudo -u estithmar ./venv/bin/pip install -r requirements.txt
sudo systemctl restart estithmar
```

If models change and you rely on PostgreSQL without Alembic migrations in-repo, plan schema updates carefully (backup first, then `db.create_all()` adds missing tables but does not alter existing columns—use manual SQL or Alembic for complex upgrades).

## 14. Backups

- **PostgreSQL (staging):** `pg_dump` on a schedule (cron) to a secure location; test restores periodically.
- **SQL Server (production):** use native backups or your hosting provider’s tooling; test restores periodically.

## 15. Checklist before going live

- [ ] Strong `ESTITHMAR_SECRET_KEY` set; `.env` not world-readable.
- [ ] Database credentials strong (PostgreSQL on staging, SQL Server on production); DB not exposed to the public internet.
- [ ] HTTPS enabled; HTTP redirects to HTTPS (Certbot can configure this).
- [ ] `dist/assets` present so the UI loads CSS/JS.
- [ ] `systemctl status estithmar` active; nginx proxying without errors in `journalctl -u estithmar -f`.

---

For local development, see [README.md](README.md).
