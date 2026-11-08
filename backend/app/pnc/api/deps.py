"""Authentication, identity resolution and the request-scoped database session.

Role and organisation are NEVER taken from a request body: they come from the signed token, are re-verified against
``app_users`` on every request, and are applied inside the transaction (SET LOCAL ROLE + app.* settings).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable

import jwt
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import Connection, text

from app.core.config import get_settings
from app.core.db import ORG, SessionContext, db_session
from app.pnc.auth_users import find_user, public_user
from app.pnc.errors import AccessDenied, NotFound, Unavailable


@dataclass(frozen=True)
class Principal:
    sub: str                 # app_users.user_id
    role: str
    org: str = ORG
    customer_id: str | None = None
    employee_id: str | None = None
    login_name: str | None = None

    @property
    def is_customer(self) -> bool:
        return self.role == "customer"

    @property
    def actor_id(self) -> str:
        """Identity used for RLS app.customer_id / app.employee_id and audit actor."""
        if self.is_customer:
            return self.customer_id or self.sub
        return self.employee_id or self.sub


def issue_token(p: Principal) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": p.sub,
            "role": p.role,
            "org": ORG,
            "customer_id": p.customer_id,
            "employee_id": p.employee_id,
            "login_name": p.login_name,
            "iat": now,
            "exp": now + timedelta(minutes=s.jwt_ttl_minutes),
        },
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )


def principal_from_user_row(row: dict) -> Principal:
    return Principal(
        sub=row["user_id"],
        role=row["role"],
        org=row.get("org", ORG),
        customer_id=row.get("customer_id"),
        employee_id=row.get("employee_id"),
        login_name=row.get("login_name"),
    )


def resolve_persona(persona_id: str) -> Principal | None:
    """Server-side lookup by login_name / user_id / customer_id / employee_id. Role comes from app_users."""
    with db_session() as conn:
        row = find_user(conn, persona_id=persona_id)
    return principal_from_user_row(row) if row else None


def load_user_profile(user_id: str) -> dict | None:
    with db_session() as conn:
        row = find_user(conn, persona_id=user_id)
    return public_user(row) if row else None


def _verify_against_db(p: Principal) -> bool:
    with db_session() as conn:
        row = find_user(conn, persona_id=p.sub)
    if not row:
        return False
    return row["role"] == p.role and row["org"] == p.org


def current_principal(authorization: str | None = Header(default=None)) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    s = get_settings()
    try:
        claims = jwt.decode(authorization.split(" ", 1)[1], s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, f"invalid token: {exc.__class__.__name__}", headers={"WWW-Authenticate": "Bearer"}) from exc
    p = Principal(
        sub=claims["sub"],
        role=claims["role"],
        org=claims.get("org", ORG),
        customer_id=claims.get("customer_id"),
        employee_id=claims.get("employee_id"),
        login_name=claims.get("login_name"),
    )
    if p.org != ORG or not _verify_against_db(p):
        raise HTTPException(401, "identity no longer valid")
    return p


def audit_denied(p: Principal, action: str, resource: str | None, reason: str, request_id: str | None = None) -> None:
    try:
        with db_session() as conn:
            conn.execute(text("SELECT log_audit_as(:a,:r,:ac,:re,NULL,NULL,'denied',false,:rid,CAST(:d AS jsonb))"),
                         {"a": p.actor_id, "r": p.role, "ac": action, "re": resource, "rid": request_id,
                          "d": json.dumps({"reason": reason})})
    except Exception:
        pass


def require_roles(*roles: str) -> Callable[..., Principal]:
    def dep(request: Request, p: Principal = Depends(current_principal)) -> Principal:
        if p.role not in roles:
            audit_denied(p, f"route.{request.method} {request.url.path}", None, "role_not_permitted")
            raise HTTPException(403, f"role '{p.role}' may not use this endpoint")
        return p
    return dep


def as_of_param(as_of: date | None = None) -> date:
    limit = date.fromisoformat(get_settings().as_of_date)
    if as_of is None:
        return limit
    if as_of > limit:
        raise HTTPException(422, f"as_of may not be after the dataset observation date {limit.isoformat()}")
    return as_of


def run(p: Principal, fn: Callable[[Connection], object], *, grant_id: str | None = None, request: Request | None = None):
    """Execute ``fn(conn)`` in a transaction scoped to the principal."""
    ctx = SessionContext(
        role=p.role,
        actor_id=p.actor_id,
        customer_id=p.customer_id if p.is_customer else None,
        employee_id=None if p.is_customer else p.employee_id,
        grant_id=grant_id,
        request_id=(request.headers.get("x-request-id") if request else None) or uuid.uuid4().hex,
    )
    err: Exception | None = None
    out = None
    with db_session(ctx) as conn:
        try:
            out = fn(conn)
        except (AccessDenied, NotFound, Unavailable, ValueError, PermissionError) as exc:
            err = exc
    if err is not None:
        if isinstance(err, AccessDenied):
            raise HTTPException(403, {"error": "access_denied", "reason": err.reason, "detail": err.detail})
        if isinstance(err, PermissionError):
            raise HTTPException(403, str(err))
        if isinstance(err, NotFound):
            raise HTTPException(404, str(err) or "not found")
        if isinstance(err, Unavailable):
            raise HTTPException(503, str(err))
        raise HTTPException(422, str(err))
    return out
