"""Authentication endpoints. Role and tabs come from ``app_users`` / ``role_catalog``, never from the client."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.config import demo_login_allowed
from app.core.db import db_session
from app.pnc.auth_users import DEMO_PASSWORD, find_user, public_user, verify_password

from .deps import Principal, current_principal, issue_token, load_user_profile, principal_from_user_row

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class DemoLoginIn(BaseModel):
    persona_id: str = Field(min_length=1, max_length=64)
    # deliberately no role field


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


def _token_payload(row: dict) -> dict:
    p = principal_from_user_row(row)
    profile = public_user(row)
    return {
        "access_token": issue_token(p),
        "token_type": "bearer",
        "user": profile,
        "warning": "Demo credentials. Default password is 'demo'. Disabled when APP_ENV=prod.",
    }


@router.post("/dev-login")
def dev_login(body: DemoLoginIn):
    """Map a persona id (C001, E101, c001, riley.chen, U-C001) → role from the database."""
    if not demo_login_allowed():
        raise HTTPException(404, "not found")
    with db_session() as conn:
        row = find_user(conn, persona_id=body.persona_id)
    if row is None:
        raise HTTPException(401, "unknown persona")
    return _token_payload(row)


@router.post("/login")
def login(body: LoginIn):
    """Username + password login against ``app_users``. Role still comes only from the database row."""
    if not demo_login_allowed():
        raise HTTPException(404, "not found")
    with db_session() as conn:
        row = find_user(conn, login_name=body.username.strip())
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "invalid username or password")
    return _token_payload(row)


@router.get("/me")
def me(p: Principal = Depends(current_principal)):
    """Current user + visible wheel tabs / home route for the UI shell."""
    profile = load_user_profile(p.sub)
    if profile is None:
        raise HTTPException(401, "identity no longer valid")
    return profile


@router.get("/personas")
def personas():
    """Demo persona directory (no secrets). Used by the persona switcher."""
    if not demo_login_allowed():
        raise HTTPException(404, "not found")
    with db_session() as conn:
        rows = conn.execute(text(
            "SELECT u.user_id, u.login_name, u.display_name, u.role, u.customer_id, u.employee_id, "
            "c.label AS role_label, c.tabs, c.home_route, c.is_staff "
            "FROM app_users u JOIN role_catalog c USING (role) "
            "WHERE u.status = 'active' ORDER BY c.is_staff, u.role, u.login_name"
        )).mappings().all()
    return {
        "default_password": DEMO_PASSWORD,
        "personas": [
            {
                "user_id": r["user_id"],
                "login_name": r["login_name"],
                "display_name": r["display_name"],
                "role": r["role"],
                "role_label": r["role_label"],
                "customer_id": r["customer_id"],
                "employee_id": r["employee_id"],
                "is_staff": r["is_staff"],
                "tabs": list(r["tabs"]),
                "home_route": r["home_route"],
            }
            for r in rows
        ],
    }
