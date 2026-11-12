import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app import create_app  # noqa: E402

H = {"X-Requested-With": "TerraWatt"}


@pytest.fixture(scope="session")
def _shared():
    return {}


@pytest.fixture()
def app(tmp_path):
    return create_app(TESTING=True, DATABASE_PATH=tmp_path / "t.db", INSTANCE_DIR=tmp_path,
                      ADMIN_EMAIL="admin@t.io", ADMIN_PASSWORD="AdminPass1")


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def user(client):
    r = client.post("/api/auth/register", json={"name": "Ada Lovelace", "email": "ada@example.com", "password": "Secret123"}, headers=H)
    assert r.status_code == 201
    return client


@pytest.fixture()
def admin(app):
    c = app.test_client()
    assert c.post("/api/auth/login", json={"email": "admin@t.io", "password": "AdminPass1"}, headers=H).status_code == 200
    return c
