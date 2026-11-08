"""One opaque, revocable session format for customer and employee logins."""
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select

from app.orm.models import User
from app.staff.store import Store, digest, now


def normalize_email(value):
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise ValueError("A valid email address is required")
    return value


def public_user(user):
    return {"user_id": user.id, "email": user.email, "login_name": user.email,
            "display_name": user.display_name, "role": user.role_key,
            "role_label": user.role.label, "tabs": user.role.tabs, "features": user.role.features,
            "customer_id": str(user.customer.tracker_id) if user.customer else None,
            "tracker_user_id": user.customer.tracker_id if user.customer else None,
            "employee_id": user.employee_id, "is_staff": user.role_key != "customer",
            "home_route": "/finance" if user.role_key == "customer" else "/"+user.role.tabs[1],
            "synthetic": user.synthetic}


def issue_session(store, user):
    token = secrets.token_urlsafe(32)
    expiry = (datetime.now(timezone.utc) + timedelta(hours=int(os.environ.get("STAFF_SESSION_HOURS", "8")))).isoformat()
    store.insert("sessions", {"id": digest(token), "user_id": user.id,
                 "employee_id": user.employee_id, "expires_at": expiry}, user.id)
    set_identity(store, user)
    store.audit("login", user.id)
    return {"access_token": token, "token": token, "token_type": "bearer", "expires_at": expiry,
            "user": public_user(user), "synthetic_demo": True}


def set_identity(store, user):
    store.user = user
    if user.role_key != "customer":
        employee = store.get("employees", user.employee_id) if user.employee_id else None
        if not employee or employee["status"] != "active":
            raise HTTPException(401, "Inactive employee")
        store.assume({**employee, "role": user.role_key})


def find_user(store, persona):
    value = persona.strip().lower()
    return store.db.scalar(select(User).where((User.email == value) | (User.id == persona)
                          | (User.employee_id == persona.upper()) | (User.id == "U"+persona)))


def database():
    with Store() as store:
        yield store


def current_identity(authorization: str | None = Header(default=None), store=Depends(database)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    record = store.get("sessions", digest(token)) if token else None
    user = store.db.get(User, record.get("user_id")) if record and record.get("user_id") else None
    if not record or record["expires_at"] <= now() or not user or not user.active:
        store.audit("access_denied", "session", "denied", reason="Invalid or expired session")
        raise HTTPException(401, "Missing, expired, or revoked session")
    set_identity(store, user)
    return store
