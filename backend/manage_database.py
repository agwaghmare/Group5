"""Create/inspect the SQLAlchemy schema or set an account's email/password locally."""
import argparse
import getpass
import json

from sqlalchemy import func, select

from app.orm.bootstrap import import_tracker
from app.orm.identity import normalize_email
from app.orm.models import Customer, DataImport, FinanceSnapshot, User
from app.pnc.auth_users import hash_password
from app.staff.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "status", "set-user"])
    parser.add_argument("--user-id", help="U1000 for tracker user 1000, or U-E001 for employee E001")
    parser.add_argument("--email")
    args = parser.parse_args()
    with Store() as store:
        if args.command == "init":
            imported = import_tracker(store.db)
            print(json.dumps({"source": imported.source, "rows": imported.row_count, "customers": imported.customer_count,
                              "columns": len(imported.columns), "idempotent": True}))
        elif args.command == "set-user":
            if not args.user_id or not args.email:
                parser.error("set-user requires --user-id and --email")
            user = store.db.get(User, args.user_id)
            if not user:
                parser.error("Unknown user ID; run status or /api/v1/auth/personas")
            email = normalize_email(args.email)
            existing = store.db.scalar(select(User).where(User.email == email, User.id != user.id))
            if existing:
                parser.error("Email is already associated with a different account")
            password = getpass.getpass("New password (minimum 12 characters): ")
            confirm = getpass.getpass("Confirm password: ")
            if len(password) < 12 or password != confirm:
                parser.error("Passwords must match and contain at least 12 characters")
            user.email, user.password_hash = email, hash_password(password)
            store.audit("local_account_updated", user.id)
            print("Updated account; no password was printed.")
        else:
            print(json.dumps({"storage": "SQLAlchemy / SQLite", "users": store.db.scalar(select(func.count()).select_from(User)),
                              "customers": store.db.scalar(select(func.count()).select_from(Customer)),
                              "snapshots": store.db.scalar(select(func.count()).select_from(FinanceSnapshot)),
                              "imports": [{"source": r.source, "rows": r.row_count, "customers": r.customer_count,
                                           "columns": r.columns, "sha256": r.sha256} for r in store.db.scalars(select(DataImport))]}))


if __name__ == "__main__":
    main()
