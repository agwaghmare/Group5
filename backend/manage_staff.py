"""Explicit, additive Tiger setup. Never run the old dataset loader for this.

Usage: python manage_staff.py init-db
Set STAFF_ADMIN_DATABASE_URL for migrations; STAFF_DATABASE_URL is runtime only.
"""
import os
import sys
from pathlib import Path

from app.settings import load_env
from app.staff.store import Store, seed


def main():
    if sys.argv[1:] != ["init-db"]:
        raise SystemExit("Usage: python manage_staff.py init-db")
    uri = os.environ.get("STAFF_ADMIN_DATABASE_URL", "")
    if not uri or "YOUR_" in uri:
        raise SystemExit("Set STAFF_ADMIN_DATABASE_URL locally; never paste credentials into source code")
    import psycopg
    root = Path(__file__).parent
    with psycopg.connect(uri) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(706310)")
        exists = conn.execute("SELECT to_regclass('staff_app.schema_migrations')").fetchone()[0]
        if exists and conn.execute("SELECT 1 FROM staff_app.schema_migrations WHERE version='staff-v1'").fetchone():
            print("Employee schema staff-v1 already installed; no changes.")
            return
        conn.execute((root / "migrations/001_staff_schema.sql").read_text())
        store = Store()
        store.postgres, store.conn = True, conn
        seed(store)
        conn.execute((root / "migrations/002_staff_security.sql").read_text())
        conn.execute("INSERT INTO staff_app.schema_migrations VALUES ('staff-v1')")
    print("Installed additive staff_app schema and synthetic seeds. Existing pnc/meta tables were not changed.")
    print("Next create a dedicated LOGIN NOINHERIT runtime user, grant finpilot_gateway to it,")
    print("and configure STAFF_DATABASE_URL with that user. Do not run the API as tsdbadmin.")


if __name__ == "__main__":
    main()
