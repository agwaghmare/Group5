"""Shared fixtures. Tests marked `db` need the TigerData service and are skipped when it is unreachable."""
from __future__ import annotations

import os
from contextlib import contextmanager

import pytest
from sqlalchemy import text

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")


def _db_available() -> bool:
    try:
        from app.core.db import get_engine, ping
        if get_engine().dialect.name != "postgresql":
            return False  # Archived Lab Package/Tiger tests do not apply to the tracker ORM.
        ping()
        return True
    except Exception:
        return False


_AVAILABLE: bool | None = None


def pytest_collection_modifyitems(config, items):
    global _AVAILABLE
    if not any(i.get_closest_marker("db") for i in items):
        return
    if _AVAILABLE is None:
        _AVAILABLE = _db_available()
    if _AVAILABLE:
        return
    skip = pytest.mark.skip(reason="Legacy PostgreSQL/Lab Package integration; inactive in local tracker ORM mode")
    for i in items:
        if i.get_closest_marker("db"):
            i.add_marker(skip)


@pytest.fixture
def rollback_session():
    """Open a session as a given identity inside a transaction that is ALWAYS rolled back."""
    from app.core.db import SessionContext, _apply_context, get_engine

    @contextmanager
    def make(role: str | None = None, actor: str | None = None, **kw):
        with get_engine().connect() as conn:
            trans = conn.begin()
            try:
                if role:
                    _apply_context(conn, SessionContext(role=role, actor_id=actor or "", **kw))
                yield conn
            finally:
                trans.rollback()
    return make


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="session")
def tokens(client):
    out: dict[str, dict] = {}

    def get(persona: str) -> dict:
        if persona not in out:
            r = client.post("/api/v1/auth/dev-login", json={"persona_id": persona})
            assert r.status_code == 200, r.text
            out[persona] = {"Authorization": f"Bearer {r.json()['access_token']}"}
        return out[persona]
    return get


@pytest.fixture
def q():
    def run(conn, sql, **params):
        return conn.execute(text(sql), params).all()
    return run
