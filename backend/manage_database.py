"""Create/inspect the SQLAlchemy schema or set an account's email/password locally."""
import argparse
import getpass
import json
import secrets

from sqlalchemy import func, select

from app.orm.accounts import provision_employee, update_account
from app.orm.bootstrap import import_tracker
from app.orm.identity import normalize_email
from app.orm.models import Customer, DataImport, FinanceSnapshot, User
from app.staff.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "status", "set-user", "create-employee", "assign-prospect"])
    parser.add_argument("--user-id", help="U1000 for tracker user 1000, or U-E001 for employee E001")
    parser.add_argument("--email")
    parser.add_argument("--name")
    parser.add_argument("--role", choices=["credit_analyst", "service_specialist", "marketing_analyst", "portfolio_manager", "compliance_analyst", "auditor", "benefits_admin"])
    parser.add_argument("--hire-date", help="YYYY-MM-DD")
    parser.add_argument("--employee-id")
    parser.add_argument("--prospect-id")
    args = parser.parse_args()
    with Store() as store:
        if args.command == "init":
            imported = import_tracker(store.db)
            print(json.dumps({"source": imported.source, "rows": imported.row_count, "customers": imported.customer_count,
                              "columns": len(imported.columns), "idempotent": True}))
        elif args.command in ("set-user", "create-employee"):
            if args.command == "create-employee":
                if not all([args.email, args.name, args.role, args.hire_date]):
                    parser.error("create-employee requires --email, --name, --role and --hire-date")
                password = getpass.getpass("New password (minimum 12 characters): ")
                if password != getpass.getpass("Confirm password: "):
                    parser.error("Passwords do not match")
                try:
                    user = provision_employee(store, normalize_email(args.email), args.name, args.role,
                        args.hire_date, password, args.employee_id or "E-"+secrets.token_hex(6))
                except ValueError as exc:
                    parser.error(str(exc))
                print(json.dumps({"user_id": user.id, "email": user.email, "role": user.role_key, "employee_id": user.employee_id}))
                return
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
            try:
                update_account(store, user, email, password, args.name, args.role, args.hire_date)
            except ValueError as exc:
                parser.error(str(exc))
            print("Updated account; no password was printed.")
        elif args.command == "assign-prospect":
            from app.orm.models import CreditProfile, Employee, Prospect
            if not args.employee_id or not args.prospect_id:
                parser.error("assign-prospect requires --employee-id and --prospect-id")
            employee = store.db.get(Employee, args.employee_id)
            user = store.db.scalar(select(User).where(User.employee_id == args.employee_id, User.active.is_(True)))
            prospect = store.db.get(Prospect, args.prospect_id)
            if not employee or not user or user.role_key != "credit_analyst" or not prospect:
                parser.error("An active Credit Analyst and an existing prospect are required")
            prospect.owner = prospect.assigned_to = args.employee_id
            prospect.payload = {**prospect.payload, "assigned_to": args.employee_id}
            profile = store.db.get(CreditProfile, prospect.id)
            if profile:
                profile.owner = args.employee_id
            store.audit("prospect_reassigned", prospect.id, assigned_to=args.employee_id)
            print("Prospect assignment updated; historical research and audit records were preserved.")
        else:
            print(json.dumps({"storage": "SQLAlchemy / SQLite", "users": store.db.scalar(select(func.count()).select_from(User)),
                              "customers": store.db.scalar(select(func.count()).select_from(Customer)),
                              "snapshots": store.db.scalar(select(func.count()).select_from(FinanceSnapshot)),
                              "imports": [{"source": r.source, "rows": r.row_count, "customers": r.customer_count,
                                           "columns": r.columns, "sha256": r.sha256} for r in store.db.scalars(select(DataImport))]}))


if __name__ == "__main__":
    main()
