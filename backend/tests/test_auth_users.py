"""app_users + role_catalog: Skill.md roles drive login and visible tabs."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.db

EXPECTED_TABS = {
    "customer": ["home", "finance", "learn"],
    "credit_analyst": ["home", "research", "benefits", "learn"],
    "service_specialist": ["home", "cases", "benefits", "learn"],
    "marketing_analyst": ["home", "portfolio", "benefits", "learn"],
    "portfolio_manager": ["home", "portfolio", "benefits", "learn"],
    "compliance_analyst": ["home", "compliance", "benefits", "learn"],
    "auditor": ["home", "compliance", "benefits", "learn"],
    "benefits_admin": ["home", "benefits", "learn"],
}


def test_role_catalog_matches_skill_md(rollback_session):
    with rollback_session() as c:
        from sqlalchemy import text
        rows = {r.role: list(r.tabs) for r in c.execute(text("SELECT role, tabs FROM role_catalog")).all()}
    assert rows == EXPECTED_TABS


def test_seeded_user_counts(rollback_session):
    with rollback_session() as c:
        from sqlalchemy import text
        n_cust = c.execute(text("SELECT count(*) FROM app_users WHERE role = 'customer'")).scalar_one()
        n_staff = c.execute(text("SELECT count(*) FROM app_users WHERE role <> 'customer'")).scalar_one()
    assert n_cust == 30
    assert n_staff >= 11   # seeded employees excluding ZZT leftovers


def test_password_login_and_me(client):
    bad = client.post("/api/v1/auth/login", json={"username": "c001", "password": "wrong"})
    assert bad.status_code == 401
    ok = client.post("/api/v1/auth/login", json={"username": "c001", "password": "demo"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["user"]["customer_id"] == "C001"
    assert body["user"]["tabs"] == ["home", "finance", "learn"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["display_name"]
    assert me.json()["home_route"] == "/finance"


def test_staff_password_login_tabs(client):
    r = client.post("/api/v1/auth/login", json={"username": "riley.chen", "password": "demo"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["role"] == "credit_analyst"
    assert r.json()["user"]["tabs"] == EXPECTED_TABS["credit_analyst"]


def test_personas_directory_lists_customers_and_staff(client):
    r = client.get("/api/v1/auth/personas")
    assert r.status_code == 200
    personas = r.json()["personas"]
    roles = {p["role"] for p in personas}
    assert "customer" in roles and "credit_analyst" in roles
    assert r.json()["default_password"] == "demo"
