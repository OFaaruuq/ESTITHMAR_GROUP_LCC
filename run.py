"""Run Istithmar Investment Management System (Flask + PostgreSQL or SQL Server).

Configure database URLs in .env (see .env.example). Run from project root:

  python run.py
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

from istithmar import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
