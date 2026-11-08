"""Local administrative provisioning; no public endpoint assigns employee roles."""
import os
from datetime import date

from sqlalchemy import delete, select

from app.orm.models import AuthSession, Employee, User
from app.pnc.auth_users import hash_password
from app.staff.registry import ROLES
from app.staff.seed import business_date


def demo_seed_enabled():
    return os.environ.get("SEED_DEMO_DATA", "false").lower() == "true" and os.environ.get("APP_ENV", "dev") != "prod"


def archive_sample_accounts(store):
    if demo_seed_enabled():
        return
    rows = list(store.db.scalars(select(User).where(User.synthetic.is_(True), User.active.is_(True), User.email.like("%@example.test"))))
    for user in rows:
        user.active = False
    if rows:
        store.db.execute(delete(AuthSession).where(AuthSession.user_id.in_([u.id for u in rows])))
        store.audit("sample_accounts_disabled", details_count=len(rows))


def provision_employee(store, email, name, role, hire_date, password, employee_id):
    if role not in ROLES:
        raise ValueError("Select a recognized employee role")
    if not name.strip() or len(name) > 150:
        raise ValueError("A display name of at most 150 characters is required")
    hired = date.fromisoformat(hire_date)
    if hired > business_date():
        raise ValueError("Hire date cannot be in the future")
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    if store.db.scalar(select(User).where(User.email == email)):
        raise ValueError("Email is already associated with an account")
    if store.db.get(Employee, employee_id):
        raise ValueError("Employee ID already exists; use set-user to adopt an existing identity")
    store.insert("employees", {"id": employee_id, "role": role, "display_name": name.strip(),
        "hire_date": hired.isoformat(), "status": "active", "synthetic": False}, employee_id)
    user = User(id="U-"+employee_id, email=email, role_key=role, employee_id=employee_id,
                password_hash=hash_password(password), display_name=name.strip(), active=True, synthetic=False)
    store.db.add(user)
    store.db.flush()
    store.audit("employee_account_provisioned", user.id, assigned_role=role)
    return user


def update_account(store, user, email, password, name=None, role=None, hire_date=None):
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    if store.db.scalar(select(User).where(User.email == email, User.id != user.id)):
        raise ValueError("Email is already associated with another account")
    if role and (role not in ROLES or not user.employee_id):
        raise ValueError("Role changes require an existing employee and a recognized employee role")
    if user.employee_id and (not name or not name.strip()):
        raise ValueError("Supply --name when adopting an employee account")
    if user.employee_id and user.synthetic and not hire_date:
        raise ValueError("Supply --hire-date when adopting a synthetic employee identity")
    hired = date.fromisoformat(hire_date) if hire_date else None
    if hired and hired > business_date():
        raise ValueError("Hire date cannot be in the future")
    user.email, user.password_hash, user.active, user.synthetic = email, hash_password(password), True, False
    if name:
        user.display_name = name.strip()
    if role:
        user.role_key = role
    if user.employee_id:
        employee = store.db.get(Employee, user.employee_id)
        employee.payload = {**employee.payload, "display_name": user.display_name, "role": user.role_key,
                            "synthetic": False, "status": "active",
                            **({"hire_date": hired.isoformat()} if hired else {})}
    store.db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    store.audit("account_updated", user.id, assigned_role=user.role_key)
