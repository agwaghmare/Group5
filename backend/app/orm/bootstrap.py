"""Validated, idempotent personal finance CSV import plus synthetic login identities."""
import csv
import hashlib
import secrets
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import Integer, Numeric, select

from app.orm.accounts import demo_seed_enabled
from app.orm.models import Customer, DataImport, Employee, FinanceSnapshot, Role, User
from app.pnc.auth_users import hash_password
from app.settings import BACKEND
from app.staff.registry import ROLES, capabilities, visible

TRACKER = BACKEND.parent / "data" / "personal_finance_tracker_dataset.csv"


def import_tracker(db, path=TRACKER):
    path = Path(path)
    if path.name != "personal_finance_tracker_dataset.csv" or "lab_package" in str(path).lower():
        raise ValueError("Only the personal finance tracker is supported; Lab Package input is not accepted")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    previous = db.get(DataImport, path.name)
    if previous and previous.sha256 == digest:
        return previous
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        expected = {col.name for col in FinanceSnapshot.__table__.columns}
        if set(columns) != expected or len(columns) != len(expected):
            raise ValueError(f"Tracker columns changed: missing={expected-set(columns)}, extra={set(columns)-expected}")
        rows = []
        seen = set()
        for line, source in enumerate(reader, start=2):
            record = {}
            try:
                for col in FinanceSnapshot.__table__.columns:
                    value = source[col.name]
                    if value is None:
                        raise ValueError("Incomplete CSV row")
                    if value == "":
                        if col.primary_key:
                            raise ValueError("Missing snapshot key")
                        parsed = None
                    elif col.name == "date":
                        parsed = date.fromisoformat(value)
                    elif isinstance(col.type, Integer):
                        parsed = int(value)
                    elif isinstance(col.type, Numeric):
                        parsed = Decimal(value)
                        if not parsed.is_finite():
                            raise ValueError("Nonfinite numeric value")
                    else:
                        parsed = value
                    record[col.name] = parsed
            except (ValueError, InvalidOperation) as exc:
                raise ValueError(f"Invalid tracker value at line {line}") from exc
            key = (record["user_id"], record["date"])
            if key in seen:
                raise ValueError(f"Duplicate snapshot key at line {line}")
            seen.add(key)
            rows.append(record)
    if not rows:
        raise ValueError("Tracker is empty")
    password = hash_password("demo" if demo_seed_enabled() else secrets.token_urlsafe(40))
    customer_ids = sorted({r["user_id"] for r in rows})
    for tracker_id in customer_ids:
        uid = f"U{tracker_id}"
        if not db.get(User, uid):
            db.add(User(id=uid, email=f"customer{tracker_id}@example.test", role_key="customer",
                        password_hash=password, active=demo_seed_enabled(), display_name=f"Synthetic customer {tracker_id}"))
            db.flush()
        if not db.get(Customer, tracker_id):
            db.add(Customer(tracker_id=tracker_id, user_id=uid))
    db.flush()
    existing = {(r.user_id, r.date): r for r in db.scalars(select(FinanceSnapshot))}
    for record in rows:
        snapshot = existing.get((record["user_id"], record["date"]))
        if snapshot is None:
            db.add(FinanceSnapshot(**record))
        else:
            for key, value in record.items():
                setattr(snapshot, key, value)
    result = previous or DataImport(source=path.name)
    result.sha256, result.row_count, result.customer_count, result.columns = digest, len(rows), len(customer_ids), columns
    db.add(result)
    db.flush()
    return result


def role_catalog():
    roles = {"customer": ("Customer", ["home", "finance", "learn"], ["fin.*", "learn.*"])}
    roles.update({key: (value[0], visible(key), capabilities(key)) for key, value in ROLES.items()})
    return roles


def sync_roles(db):
    """Create missing roles and move an existing credit analyst off Learn/Wilbur.

    Other stored feature lists stay as written. A database grant that is narrower
    than the code registry must keep failing closed.
    """
    for key, (label, tabs, features) in role_catalog().items():
        role = db.get(Role, key)
        if not role:
            db.add(Role(key=key, label=label, tabs=tabs, features=features))
            continue
        outdated = key == "credit_analyst" and (
            list(role.tabs or []) != tabs or "learn.explain" in (role.features or []) or "learn" in (role.tabs or [])
        )
        if outdated:
            role.label, role.tabs, role.features = label, tabs, features
    db.flush()


def seed_identities(db):
    sync_roles(db)
    password = hash_password("demo" if demo_seed_enabled() else secrets.token_urlsafe(40))
    for employee in db.scalars(select(Employee)):
        if not db.get(User, "U-"+employee.id):
            db.add(User(id="U-"+employee.id, email=employee.id.lower()+"@example.test",
                        role_key=employee.payload["role"], employee_id=employee.id,
                        password_hash=password, active=demo_seed_enabled(), display_name=employee.payload["display_name"]))
    db.flush()
    if not db.get(DataImport, TRACKER.name):
        import_tracker(db)
