"""SQLAlchemy-backed employee persistence; authorization is enforced by the API."""
import hashlib
import json
import secrets
import threading
from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.orm.accounts import archive_sample_accounts, demo_seed_enabled
from app.orm.authorization import authorize_write, redact, scoped_query
from app.orm.bootstrap import seed_identities
from app.orm.database import database_url, get_engine
from app.orm.models import RECORD_MODELS, DataImport, Role
from app.staff.policy import ALLOWED, POLICY
from app.staff.registry import FEATURES
from app.staff.seed import catalog, employees, prospects

TABLES = ("employees", "prospects", "credit_profiles", "protected", "links", "policies", "grants", "runs", "decisions",
          "cases", "case_events", "catalog", "benefit_rules", "redemptions", "audit", "sessions", "campaigns", "anomalies", "permissions")
_INIT = threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat()


def ident(prefix):
    return f"{prefix}-{secrets.token_hex(12)}"


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def seed(store):
    if store.get("permissions", "staff.access"):
        return
    if demo_seed_enabled():
        for employee in employees():
            store.insert("employees", employee, employee["id"])
        for i, prospect in enumerate(prospects()):
            metadata = {k: prospect[k] for k in ("id", "product", "application_ref", "assigned_to", "synthetic", "as_of")}
            store.insert("prospects", metadata, prospect["assigned_to"])
            store.insert("credit_profiles", {k: v for k, v in prospect.items() if k in (*ALLOWED, "id", "employment_months", "delinquencies_12m", "bankruptcy_years_ago")}, prospect["assigned_to"])
            store.insert("protected", {"id": prospect["id"], "group_label": "A" if i % 2 else "B"})
        store.insert("links", {"id": "conflict-demo", "employee_id": "E001", "prospect_id": "P005"}, "E001")
    store.insert("policies", POLICY)
    for item in catalog():
        store.insert("catalog", {**item, "item_key": item["id"]})
    store.insert("benefit_rules", {"id": "benefits-v1", "version": 1,
        "tiers": [{"min_months": 0, "rate": 10}, {"min_months": 12, "rate": 15}, {"min_months": 60, "rate": 20}],
        "annual_cap_cents": 150000, "quarterly_item_limit": 2, "synthetic": True})
    if demo_seed_enabled():
        for i in range(2):
            store.insert("cases", {"id": f"CASE-{i+1:03}", "customer_id": str(1000+i),
                "reason": "Consented synthetic hardship handoff", "consented_context": "Customer requests help reviewing reduced income and upcoming bills. No sales consent.",
                "status": "new", "assigned_to": "E003", "created_at": now(), "sla_due": "2026-11-09T17:00:00+00:00",
                "source_agent": "personal_finance", "source_type": "seeded_handoff", "synthetic": True}, "E003")
    for feature, roles in FEATURES.items():
        store.insert("permissions", {"id": feature, "roles": roles})


class Store:
    """SQLAlchemy transaction shared by identity, tracker and employee services."""
    def __init__(self):
        self.employee = None
        self.user = None
        self.postgres = False  # Legacy branches are inactive; no Tiger functions run.
        self.url = database_url()

    def __enter__(self):
        with _INIT:
            self.db = Session(get_engine(), expire_on_commit=False)
            try:
                self.db.execute(text("BEGIN IMMEDIATE"))
                seed(self)
                if not self.db.get(Role, "customer") or not self.db.get(DataImport, "personal_finance_tracker_dataset.csv"):
                    seed_identities(self.db)
                archive_sample_accounts(self)
                self.db.commit()
            except Exception:
                self.db.rollback()
                self.db.close()
                raise
        self.db.execute(text("BEGIN IMMEDIATE"))
        return self

    def __exit__(self, cls, error, tb):
        from fastapi import HTTPException
        try:
            if error is None or isinstance(error, HTTPException):
                self.db.commit()
            else:
                self.db.rollback()
        finally:
            self.db.close()

    def execute(self, query, args=()):
        # Internal compatibility for existing expiry/immutability tests, not an API.
        if args:
            return self.db.connection().exec_driver_sql(query.replace("%s", "?"), args)
        return self.db.execute(text(query))

    def table(self, name):
        if name not in RECORD_MODELS:
            raise ValueError("Unknown table")
        return '"'+name+'"'

    def assume(self, employee):
        self.employee = employee

    def all(self, table):
        return [redact(self, table, deepcopy(row.payload)) for row in self.db.scalars(scoped_query(self, table).order_by(RECORD_MODELS[table].id))]

    def get(self, table, key):
        row = self.db.scalar(scoped_query(self, table).where(RECORD_MODELS[table].id == key))
        return redact(self, table, deepcopy(row.payload)) if row else None

    def insert(self, table, data, owner=""):
        authorize_write(self, table, data, owner)
        json.dumps(data, allow_nan=False)
        model = RECORD_MODELS[table]
        fields = {col.name: data[col.name] for col in model.__table__.columns
                  if col.name not in ("id", "owner", "payload") and col.name in data}
        self.db.add(model(id=data["id"], owner=owner, payload=deepcopy(data), **fields))
        self.db.flush()
        return data

    def update(self, table, data):
        if table not in ("cases", "anomalies", "grants", "sessions"):
            raise ValueError("This resource is append-only")
        row = self.db.get(RECORD_MODELS[table], data["id"])
        if row is None:
            raise KeyError(data["id"])
        authorize_write(self, table, data, row.owner, update=True)
        row.payload = deepcopy(data)
        for col in row.__table__.columns:
            if col.name not in ("id", "owner", "payload") and col.name in data:
                setattr(row, col.name, data[col.name])
        self.db.flush()
        return data

    def audit(self, action, resource="", outcome="allowed", **details):
        row = {"id": ident("AUD"), "ts": now(),
               "actor": (self.user.id if self.user else (self.employee or {}).get("id", "anonymous")),
               "role": (self.user.role_key if self.user else (self.employee or {}).get("role", "anonymous")),
               "action": action, "resource": resource, "outcome": outcome, **details}
        self.insert("audit", row)
        return row
