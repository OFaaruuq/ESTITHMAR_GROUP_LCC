"""Run Estithmar Investment Management System (Flask + PostgreSQL or SQL Server).

Configure database URLs in .env (see .env.example). Run from project root:

  python run.py

Uses Waitress (production-ready WSGI on Windows). For local dev with auto-reload, use ``flask run``.
"""
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _root)

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_root, ".flaskenv"))
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    pass

from estithmar import create_app

app = create_app()

if __name__ == "__main__":
    from waitress import serve

    host = os.environ.get("WAITRESS_HOST", "0.0.0.0")
    port = int(os.environ.get("WAITRESS_PORT", os.environ.get("PORT", "5000")))
    serve(app, host=host, port=port)
