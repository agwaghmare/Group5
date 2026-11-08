"""Probe the TigerData service: versions, privileges, extension and RLS support."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.db import db_session  # noqa: E402


def main() -> None:
    with db_session() as conn:
        print(conn.execute(text("select version()")).scalar()[:70])
        print("timescaledb:", conn.execute(text("select extversion from pg_extension where extname='timescaledb'")).scalar())
        print(
            "current role:",
            conn.execute(
                text("select rolname, rolcreaterole, rolsuper, rolbypassrls from pg_roles where rolname=current_user")
            ).one(),
        )
        print("app roles:", conn.execute(text("select string_agg(rolname, ',') from pg_roles where rolname like 'app\\_%'")).scalar())
        print("extensions:", conn.execute(text("select string_agg(extname, ',') from pg_extension")).scalar())
        print("schemas:", conn.execute(text("select string_agg(nspname, ',') from pg_namespace where nspname not like 'pg\\_%' and nspname<>'information_schema'")).scalar())


if __name__ == "__main__":
    main()
