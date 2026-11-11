"""Tests run against their own database, rebuilt and reseeded once per run.

Set TEST_DATABASE_URL to use a different one. The development database is never touched.
"""
import os

TEST_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://localhost:5432/tdra_gov_test")
os.environ["DATABASE_URL"] = TEST_URL
os.environ["LLM_MODE"] = "mock"

import psycopg  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _ensure_database() -> None:
    base, _, name = TEST_URL.rpartition("/")
    with psycopg.connect(f"{base}/postgres", autocommit=True) as connection:
        if not connection.execute("select 1 from pg_database where datname = %s", (name,)).fetchone():
            connection.execute(f'create database "{name}"')


@pytest.fixture(scope="session", autouse=True)
def seeded_database():
    _ensure_database()
    from app.db import make_sync_session
    from app.seed.__main__ import reset_schema, seed

    reset_schema()
    session = make_sync_session()
    seed(session)
    session.commit()
    session.close()


@pytest.fixture(scope="session")
def client(seeded_database):
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def login(client):
    def _login(email: str) -> dict:
        response = client.post("/auth/login", json={"email": email})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login


@pytest.fixture(scope="session")
def auth(login):
    return login("noura.alketbi@hrl.gov.example")
