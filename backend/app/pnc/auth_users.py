"""App-user identities and role → view mapping (Skill.md §3.1 / §3.5).

Passwords are demo-only (default ``demo``). Role and organisation are never taken from a request body.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

from sqlalchemy import text

from app.core.db import db_session

DEMO_PASSWORD = "demo"
_PBKDF2_ROUNDS = 120_000


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds_s, salt_hex, digest_hex = stored.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds_s))
    return hmac.compare_digest(check.hex(), digest_hex)


def _login_from_name(display_name: str) -> str:
    parts = [p for p in display_name.lower().replace("'", "").split() if p.isalpha() or p.replace("-", "").isalpha()]
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[-1]}"
    return parts[0] if parts else "user"


def seed_users(password: str = DEMO_PASSWORD) -> dict[str, int]:
    """Idempotent seed: one app_user per customer + each real employee (skips ZZT-* test leftovers)."""
    pw = hash_password(password)
    customers = employees = 0
    with db_session() as s:
        for cid, name in s.execute(text("SELECT customer_id, display_name FROM pnc_customers ORDER BY 1")):
            login = cid.lower()
            s.execute(text(
                "INSERT INTO app_users(user_id, login_name, password_hash, role, display_name, customer_id, source_type) "
                "VALUES (:u,:l,:p,'customer',:n,:c,'synthetic_demo') "
                "ON CONFLICT (user_id) DO UPDATE SET login_name = EXCLUDED.login_name, display_name = EXCLUDED.display_name, "
                "password_hash = EXCLUDED.password_hash, status = 'active'"),
                {"u": f"U-{cid}", "l": login, "p": pw, "n": name, "c": cid})
            customers += 1
        for eid, name, role in s.execute(text(
                "SELECT employee_id, display_name, role FROM employees "
                "WHERE status = 'active' AND employee_id NOT LIKE 'ZZT-%' ORDER BY 1")):
            login = _login_from_name(name)
            # avoid colliding with a customer login
            if s.execute(text("SELECT 1 FROM app_users WHERE login_name = :l AND user_id <> :u"),
                         {"l": login, "u": f"U-{eid}"}).first():
                login = f"{login}.{eid.lower()}"
            s.execute(text(
                "INSERT INTO app_users(user_id, login_name, password_hash, role, display_name, employee_id, source_type) "
                "VALUES (:u,:l,:p,:r,:n,:e,'synthetic_demo') "
                "ON CONFLICT (user_id) DO UPDATE SET login_name = EXCLUDED.login_name, display_name = EXCLUDED.display_name, "
                "role = EXCLUDED.role, password_hash = EXCLUDED.password_hash, status = 'active'"),
                {"u": f"U-{eid}", "l": login, "p": pw, "r": role, "n": name, "e": eid})
            employees += 1
    return {"customers": customers, "employees": employees, "password": password}


def find_user(conn, *, login_name: str | None = None, persona_id: str | None = None) -> dict[str, Any] | None:
    """Resolve an active user by login_name, user_id, customer_id, or employee_id."""
    if login_name:
        row = conn.execute(text(
            "SELECT u.*, c.label AS role_label, c.tabs, c.home_route, c.features, c.is_staff "
            "FROM app_users u JOIN role_catalog c USING (role) "
            "WHERE u.status = 'active' AND lower(u.login_name) = lower(:l)"),
            {"l": login_name}).mappings().first()
        return dict(row) if row else None
    if not persona_id:
        return None
    pid = persona_id.strip()
    row = conn.execute(text(
        "SELECT u.*, c.label AS role_label, c.tabs, c.home_route, c.features, c.is_staff "
        "FROM app_users u JOIN role_catalog c USING (role) "
        "WHERE u.status = 'active' AND ("
        "  u.user_id = :p OR u.customer_id = :p OR u.employee_id = :p OR lower(u.login_name) = lower(:p)"
        ")"), {"p": pid}).mappings().first()
    return dict(row) if row else None


def public_user(row: dict[str, Any]) -> dict[str, Any]:
    """Shape returned to the client: enough to pick the view, never the password hash."""
    return {
        "user_id": row["user_id"],
        "login_name": row["login_name"],
        "display_name": row["display_name"],
        "role": row["role"],
        "role_label": row["role_label"],
        "org": row["org"],
        "customer_id": row["customer_id"],
        "employee_id": row["employee_id"],
        "is_staff": bool(row["is_staff"]),
        "tabs": list(row["tabs"]),
        "home_route": row["home_route"],
        "features": list(row["features"]),
    }
