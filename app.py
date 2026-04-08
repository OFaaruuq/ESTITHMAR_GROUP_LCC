"""
Flask application for `flask run` and WSGI servers.

Always run commands from the project root::

    Admin\\istithmar_app

Examples (venv activated)::

    flask run
    python run.py
    .\\run-dev.ps1
"""
from istithmar import create_app, db, migrate

app = create_app()
