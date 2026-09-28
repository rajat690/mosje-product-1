"""Test setup. Default: a fresh SQLite file. Set TEST_DATABASE_URL=postgresql://... to run the same
tests against PostgreSQL (the test database is wiped)."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dashboard"))

_tmp = tempfile.mkdtemp(prefix="mosje_test_")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["API_KEY"] = "test-key"
os.environ["RUN_STARTUP_TASKS"] = "false"

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from db.engine import get_engine  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    eng = get_engine()
    if eng.dialect.name == "postgresql":          # start from an empty schema
        with eng.begin() as c:
            c.execute(text("DROP SCHEMA public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
    return eng


@pytest.fixture(scope="session")
def client(engine):
    from fastapi.testclient import TestClient
    from api.main import app
    with TestClient(app) as c:
        yield c


H = {"X-API-Key": "test-key"}


@pytest.fixture(scope="session")
def seeded(client):
    r = client.post("/admin/seed", headers=H)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def run(client, seeded):
    r = client.post("/pipeline/run?wait=true", headers=H)
    assert r.status_code == 200, r.text
    return r.json()
