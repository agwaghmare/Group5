"""Transactional demo store; optional PostgreSQL uses explicit migrations and RLS.

SQLite deliberately provides API-only isolation. It is never presented as proof
of the Tiger role policies. Configure STAFF_DATABASE_URL to use PostgreSQL.
"""
import hashlib
import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.settings import BACKEND
from app.staff.policy import ALLOWED, POLICY
from app.staff.registry import FEATURES, ROLES
from app.staff.seed import AS_OF, catalog, employees, prospects

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
    if store.all("employees"):
        return
    for employee in employees():
        store.insert("employees", employee, employee["id"])
    for i, prospect in enumerate(prospects()):
        metadata = {k: prospect[k] for k in ("id", "product", "application_ref", "assigned_to", "synthetic", "as_of")}
        store.insert("prospects", metadata, prospect["assigned_to"])
        store.insert("credit_profiles", {k: v for k, v in prospect.items() if k in (*ALLOWED, "id")}, prospect["assigned_to"])
        store.insert("protected", {"id": prospect["id"], "group_label": "A" if i % 2 else "B"})
    store.insert("links", {"id": "conflict-demo", "employee_id": "E001", "prospect_id": "P005"}, "E001")
    store.insert("policies", POLICY)
    for item in catalog():
        store.insert("catalog", {**item, "item_key": item["id"]})
    store.insert("benefit_rules", {"id": "benefits-v1", "version": 1,
        "tiers": [{"min_months": 0, "rate": 10}, {"min_months": 12, "rate": 15}, {"min_months": 60, "rate": 20}],
        "annual_cap_cents": 150000, "quarterly_item_limit": 2, "synthetic": True})
    for i in range(2):
        store.insert("cases", {"id": f"CASE-{i+1:03}", "customer_id": str(1000+i),
            "reason": "Consented synthetic hardship handoff", "consented_context": "Customer requests help reviewing reduced income and upcoming bills. No sales consent.",
            "status": "new", "assigned_to": "E003", "created_at": now(), "sla_due": "2026-11-09T17:00:00+00:00",
            "source_agent": "personal_finance", "source_type": "seeded_handoff", "synthetic": True}, "E003")
    for feature, roles in FEATURES.items():
        store.insert("permissions", {"id": feature, "roles": roles})


class Store:
    def __init__(self):
        self.url = os.environ.get("STAFF_DATABASE_URL", "").strip()
        self.postgres = bool(self.url)
        self.employee = None

    def __enter__(self):
        if self.postgres:
            try:
                import psycopg
            except ImportError as exc:
                raise RuntimeError("Install backend requirements to enable PostgreSQL") from exc
            self.conn = psycopg.connect(self.url)
            privileged = self.conn.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()[0]
            if privileged:
                self.conn.close()
                raise RuntimeError("Use a dedicated non-superuser runtime login without BYPASSRLS; never use tsdbadmin for the staff API")
            owner = self.conn.execute("SELECT EXISTS(SELECT FROM pg_tables WHERE schemaname='staff_app' AND tableowner=current_user)").fetchone()[0]
            if owner:
                self.conn.close()
                raise RuntimeError("The migration owner cannot be the staff API runtime login")
            self.conn.execute("SET LOCAL ROLE finpilot_gateway")
        else:
            path = Path(os.environ.get("STAFF_SQLITE_PATH", BACKEND / "storage" / "staff.sqlite3"))
            path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(path, timeout=20)
            self.conn.execute("PRAGMA foreign_keys=ON")
            with _INIT:
                for table in TABLES:
                    self.conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" (id TEXT PRIMARY KEY, owner TEXT NOT NULL DEFAULT \'\', payload TEXT NOT NULL)')
                for table in ("audit", "runs", "decisions", "case_events", "redemptions", "policies", "benefit_rules", "catalog"):
                    for operation in ("UPDATE", "DELETE"):
                        self.conn.execute(f'CREATE TRIGGER IF NOT EXISTS "immutable_{table}_{operation}" BEFORE {operation} ON "{table}" BEGIN SELECT RAISE(ABORT, \'append-only\'); END')
                self.conn.commit()
                self.conn.execute("BEGIN IMMEDIATE")
                seed(self)
                self.conn.commit()
            self.conn.execute("BEGIN IMMEDIATE")
        return self

    def __exit__(self, cls, error, tb):
        # HTTP errors retain the denial audit. Routes validate before mutating.
        from fastapi import HTTPException
        try:
            if error is None or isinstance(error, HTTPException):
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self.conn.close()

    def execute(self, query, args=()):
        if not self.postgres:
            query = query.replace("%s", "?")
        return self.conn.execute(query, args)

    def table(self, name):
        if name not in TABLES:
            raise ValueError("Unknown table")
        if self.postgres and name == "runs" and self.employee and self.employee["role"] == "compliance_analyst":
            return "staff_app.review_runs"
        return f'staff_app."{name}"' if self.postgres else f'"{name}"'

    def assume(self, employee):
        self.employee = employee
        if self.postgres:
            role = employee["role"]
            if role not in ROLES:
                raise ValueError("Unknown role")
            self.conn.execute(f"SET LOCAL ROLE app_{role}")
            self.conn.execute("SELECT set_config('app.employee_id', %s, true)", (employee["id"],))
            # Serializes cap checks per employee, without locking other employees.
            self.conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (employee["id"],))

    def all(self, table):
        rows = self.execute(f"SELECT payload FROM {self.table(table)} ORDER BY id").fetchall()
        return [r[0] if isinstance(r[0], dict) else json.loads(r[0]) for r in rows]

    def get(self, table, key):
        row = self.execute(f"SELECT payload FROM {self.table(table)} WHERE id=%s", (key,)).fetchone()
        return (row[0] if isinstance(row[0], dict) else json.loads(row[0])) if row else None

    def insert(self, table, data, owner=""):
        payload = json.dumps(data, allow_nan=False)
        self.execute(f"INSERT INTO {self.table(table)} (id, owner, payload) VALUES (%s,%s,%s)", (data["id"], owner, payload))
        return data

    def update(self, table, data):
        if table not in ("cases", "anomalies"):
            raise ValueError("This resource is append-only")
        self.execute(f"UPDATE {self.table(table)} SET payload=%s WHERE id=%s", (json.dumps(data), data["id"]))
        return data

    def audit(self, action, resource="", outcome="allowed", **details):
        row = {"id": ident("AUD"), "ts": now(), "actor": (self.employee or {}).get("id", "anonymous"),
               "role": (self.employee or {}).get("role", "anonymous"), "action": action,
               "resource": resource, "outcome": outcome, **details}
        if self.postgres:
            self.conn.execute("SELECT staff_app.write_audit(%s::jsonb)", (json.dumps(row),))
        else:
            self.insert("audit", row)
        return row
