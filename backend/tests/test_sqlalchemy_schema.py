"""Real local schema, source-fidelity and role-boundary integration tests."""
import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.orm.bootstrap import TRACKER, import_tracker
from app.orm.database import get_engine
from app.orm.models import Customer, DataImport, FinanceSnapshot, Role, User
from app.staff.registry import visible
from app.staff.store import Store


@pytest.fixture
def local(monkeypatch, tmp_path):
    monkeypatch.setenv("STAFF_SQLITE_PATH", str(tmp_path / "app.sqlite3"))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DEMO_LOGIN_ENABLED", "true")
    monkeypatch.setenv("STAFF_DEMO_ENABLED", "true")
    with TestClient(app) as client:
        yield client


def login(client, persona):
    response = client.post("/api/v1/auth/dev-login", json={"persona_id": str(persona)})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_every_column_and_every_imported_value_matches_source(local):
    assert local.get("/health/db").status_code == 200
    with TRACKER.open() as handle:
        reader = csv.DictReader(handle)
        source_columns = set(reader.fieldnames)
        source = {(int(r["user_id"]), date.fromisoformat(r["date"])): r for r in reader}
    assert len(source_columns) == 44
    assert {col.name for col in FinanceSnapshot.__table__.columns} == source_columns
    with Store() as store:
        assert store.db.scalar(select(func.count()).select_from(User)) == 508
        assert store.db.scalar(select(func.count()).select_from(Customer)) == 500
        rows = list(store.db.scalars(select(FinanceSnapshot)))
        assert len(rows) == len(source) == 3000
        for row in rows:
            expected = source[(row.user_id, row.date)]
            for field in source_columns:
                actual = getattr(row, field)
                value = expected[field]
                if isinstance(actual, Decimal):
                    assert actual == Decimal(value), (field, row.user_id, row.date)
                elif isinstance(actual, int):
                    assert actual == int(value)
                elif isinstance(actual, date):
                    assert actual == date.fromisoformat(value)
                else:
                    assert actual == (value or None)
        metadata = store.db.get(DataImport, TRACKER.name)
        assert metadata.row_count == 3000 and metadata.customer_count == 500
        assert set(metadata.columns) == source_columns


def test_idempotency_and_no_lab_package_access(local, monkeypatch, tmp_path):
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert "lab_package" not in str(path).lower(), "Lab Package must not be read"
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded)
    monkeypatch.setenv("STAFF_SQLITE_PATH", str(tmp_path / "no_lab.sqlite3"))
    with Store() as store:
        first = import_tracker(store.db)
        second = import_tracker(store.db)
        assert first.sha256 == second.sha256
        assert store.db.scalar(select(func.count()).select_from(FinanceSnapshot)) == 3000
        assert list(store.db.scalars(select(DataImport.source))) == [TRACKER.name]


def test_schema_foreign_keys_and_email_uniqueness(local):
    local.get("/health/db")
    inspector = inspect(get_engine())
    assert any(f["referred_table"] == "roles" for f in inspector.get_foreign_keys("users"))
    assert any(f["referred_table"] == "customers" for f in inspector.get_foreign_keys("finance_snapshots"))
    assert any(f["referred_table"] == "prospects" for f in inspector.get_foreign_keys("credit_profiles"))
    with Store() as store:
        original = store.db.get(User, "U1000")
        with pytest.raises(IntegrityError), store.db.begin_nested():
            store.db.add(User(id="duplicate", email=original.email, role_key="customer", password_hash="x", display_name="Duplicate"))
            store.db.flush()
        with pytest.raises(IntegrityError), store.db.begin_nested():
            store.db.add(User(id="unknown-role", email="unknown@example.test", role_key="admin", password_hash="x", display_name="Unknown"))
            store.db.flush()
        with pytest.raises(IntegrityError), store.db.begin_nested():
            store.db.add(User(id="uppercase", email="UPPER@example.test", role_key="customer", password_hash="x", display_name="Upper"))
            store.db.flush()
        assert len(list(store.db.scalars(select(Role)))) == 8


def test_email_login_and_server_authoritative_role(local):
    response = local.post("/api/v1/auth/login", json={"email": " CUSTOMER1000@EXAMPLE.TEST ", "password": "demo"})
    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] == "customer1000@example.test"
    assert response.json()["user"]["role"] == "customer"
    assert "password_hash" not in response.text
    assert local.post("/api/v1/auth/login", json={"email": "customer1000@example.test", "password": "wrong"}).status_code == 401
    assert local.post("/api/v1/auth/login", json={"email": "customer1000@example.test", "password": "demo", "role": "auditor"}).status_code == 422
    h = {"Authorization": "Bearer " + response.json()["access_token"]}
    assert local.get("/api/v1/auth/me", headers=h).json()["role"] == "customer"
    assert local.delete("/api/v1/auth/session", headers=h).status_code == 204
    assert local.get("/api/v1/auth/me", headers=h).status_code == 401


def test_customer_gets_all_columns_but_only_own_rows(local):
    h = login(local, 1000)
    response = local.get("/api/v1/pnc/tracker", headers=h)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 6
    assert len(data["columns"]) == 44
    assert all(set(row) == set(data["columns"]) and row["user_id"] == 1000 for row in data["snapshots"])
    profile = local.get("/api/v1/pnc/profile", headers=h).json()
    assert set(data["columns"]).issubset(profile)
    assert local.get("/api/v1/pnc/tracker", params={"customer_id": "1001"}, headers=h).status_code == 403
    assert local.get("/api/v1/pnc/profile", params={"customer_id": "1001"}, headers=h).status_code == 403
    assert local.get("/api/v1/pnc/tracker").status_code == 401
    assert local.get("/staff/prospects", headers=h).status_code == 403


def test_personalized_learn_cannot_bypass_ownership(local):
    h = login(local, 1000)
    request = {"question": "Explain APY", "tracker_user_id": 1000}
    assert local.post("/learn/context/explain", json=request).status_code == 401
    assert local.post("/learn/context/explain", json=request, headers=h).status_code == 200
    request["tracker_user_id"] = 1001
    assert local.post("/learn/context/explain", json=request, headers=h).status_code == 403
    assert local.get("/learn/context/prompts", params={"tracker_user_id": 1001}, headers=h).status_code == 403
    employee = login(local, "E001")
    assert local.post("/learn/agent", json=request, headers=employee).status_code == 403


def test_all_eight_roles_have_their_own_view(local):
    people = local.get("/api/v1/auth/personas").json()["personas"]
    assert len(people) == 508
    for employee, role in [("1000", "customer"), ("E001", "credit_analyst"), ("E003", "service_specialist"),
                           ("E004", "marketing_analyst"), ("E005", "portfolio_manager"),
                           ("E006", "compliance_analyst"), ("E007", "auditor"), ("E008", "benefits_admin")]:
        h = login(local, employee)
        result = local.get("/api/v1/view", headers=h)
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["user"]["role"] == role
        assert body["tabs"] == (["home", "finance", "learn"] if role == "customer" else visible(role))
        if role != "customer":
            assert local.get("/api/v1/pnc/tracker", headers=h).status_code == 403
            assert local.get("/staff/me", headers=h).json()["user"]["role"] == role
        if role == "credit_analyst":
            assert "annual_income" not in str(body["data"])


def test_unified_email_login_can_run_credit_research(local):
    result = local.post("/api/v1/auth/login", json={"email": "e001@example.test", "password": "demo"})
    h = {"Authorization": "Bearer " + result.json()["access_token"]}
    assert local.get("/staff/prospects", headers=h).status_code == 200
    grant = local.post("/staff/access-grants", json={"prospect_id": "P001", "purpose": "application_review", "reference_id": "APP-001"}, headers=h)
    assert grant.status_code == 201, grant.text
    profile = local.get("/staff/prospects/P001", params={"grant_id": grant.json()["id"]}, headers=h)
    assert profile.status_code == 200
    assert "annual_income" in profile.json()["prospect"]
    assert all(key not in profile.json()["prospect"] for key in ("age", "name", "city", "group_label"))
    run = local.post("/staff/research-runs", json={"grant_id": grant.json()["id"]}, headers=h)
    assert run.status_code == 201 and run.json()["validation"]["passed"]
    decision = local.post("/staff/decisions", json={"run_id": run.json()["id"],
        "decision": run.json()["recommended_human_action"], "rationale": "Reviewed the allowed synthetic policy evidence."}, headers=h)
    assert decision.status_code == 201, decision.text
    assert decision.json()["sent_externally"] is False


def test_role_changes_and_disabled_users_apply_to_existing_tokens(local):
    h = login(local, "E001")
    with Store() as store:
        user = store.db.get(User, "U-E001")
        user.role_key = "portfolio_manager"
    assert local.get("/staff/prospects", headers=h).status_code == 403
    assert local.get("/api/v1/auth/me", headers=h).json()["role"] == "portfolio_manager"
    with Store() as store:
        store.db.get(User, "U-E001").active = False
    assert local.get("/api/v1/auth/me", headers=h).status_code == 401
