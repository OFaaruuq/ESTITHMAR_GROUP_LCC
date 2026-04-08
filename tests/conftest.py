"""Pytest uses PostgreSQL only (see get_test_database_uri in istithmar.config)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


@pytest.fixture
def app():
    from istithmar import create_app
    from istithmar.config import get_test_database_uri

    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": get_test_database_uri(),
        }
    )
    yield application
