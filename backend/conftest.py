# Shared pytest fixtures for API integration tests

import os
import tempfile

# point the app at a throwaway SQLite file instead of real Postgres database
# and give auth.py a JWT secret to sign tokens with.

_test_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_file.name}"
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")

import pytest
from fastapi.testclient import TestClient

from app.db import engine
from app.models import Base
from app.main import app

@pytest.fixture()
def client():
    # A fresh TestClient per test, with a completely empty database each time.

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c