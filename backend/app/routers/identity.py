"""Email login and role/view directory backed by SQLAlchemy User and Role."""
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.orm.identity import current_identity, database, find_user, issue_session, normalize_email, public_user
from app.orm.models import User
from app.pnc.auth_users import verify_password
from app.staff.store import digest

router = APIRouter(prefix="/api/v1/auth", tags=["Users and roles"])


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str | None = Field(default=None, max_length=254)
    username: str | None = Field(default=None, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class DemoLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    persona_id: str = Field(min_length=1, max_length=254)


def require_demo():
    if os.environ.get("APP_ENV", "dev") == "prod" or os.environ.get("DEMO_LOGIN_ENABLED", "true").lower() != "true":
        raise HTTPException(404, "Demo login is disabled")


@router.post("/login")
def login(body: Login, store=Depends(database)):
    try:
        email = normalize_email(body.email or body.username or "")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    user = store.db.scalar(select(User).where(User.email == email))
    if not user or not user.active or not verify_password(body.password, user.password_hash):
        store.audit("login_failed", "email_login", "denied")
        raise HTTPException(401, "Invalid email or password")
    return issue_session(store, user)


@router.post("/dev-login")
def demo_login(body: DemoLogin, store=Depends(database)):
    require_demo()
    user = find_user(store, body.persona_id)
    if not user or not user.active:
        raise HTTPException(401, "Unknown demo persona; use a tracker ID such as 1000 or an employee ID such as E001")
    return issue_session(store, user)


@router.get("/personas")
def personas(store=Depends(database)):
    require_demo()
    return {"personas": [public_user(u) for u in store.db.scalars(select(User).where(User.active.is_(True)).order_by(User.role_key, User.email))],
            "synthetic_demo": True, "default_password": "demo"}


@router.get("/me")
def me(store=Depends(current_identity)):
    store.audit("identity_read", store.user.id)
    return public_user(store.user)


@router.delete("/session", status_code=204)
def logout(authorization: str = Header(), store=Depends(current_identity)):
    from app.orm.models import AuthSession
    row = store.db.get(AuthSession, digest(authorization.removeprefix("Bearer ")))
    if row:
        store.db.delete(row)
    store.audit("logout")
    return Response(status_code=204)
