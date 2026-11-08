"""Disposable experiment: does RLS + SET LOCAL ROLE behave correctly on THIS TigerData service,
including on hypertables? Creates and removes a scratch schema and role."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.db import db_session  # noqa: E402


def main() -> None:
    results: dict[str, object] = {}
    with db_session() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS rls_probe CASCADE"))
        conn.execute(text("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='rls_probe_role') THEN CREATE ROLE rls_probe_role NOLOGIN; END IF; END $$"))
        conn.execute(text("GRANT rls_probe_role TO current_user"))
        conn.execute(text("CREATE SCHEMA rls_probe"))
        conn.execute(text("GRANT USAGE ON SCHEMA rls_probe TO rls_probe_role"))
        conn.execute(text("CREATE TABLE rls_probe.ht (id bigint, ts timestamptz NOT NULL, owner text NOT NULL, PRIMARY KEY (id, ts))"))
        conn.execute(text("SELECT create_hypertable('rls_probe.ht', 'ts')"))
        conn.execute(text("CREATE TABLE rls_probe.reg (id bigint PRIMARY KEY, owner text)"))
        for t in ("ht", "reg"):
            conn.execute(text(f"ALTER TABLE rls_probe.{t} ENABLE ROW LEVEL SECURITY"))
            conn.execute(text(f"ALTER TABLE rls_probe.{t} FORCE ROW LEVEL SECURITY"))
            conn.execute(text(f"GRANT SELECT, INSERT ON rls_probe.{t} TO rls_probe_role"))
            conn.execute(
                text(
                    f"CREATE POLICY p_{t} ON rls_probe.{t} FOR ALL TO rls_probe_role "
                    "USING (owner = current_setting('app.actor_id', true)) "
                    "WITH CHECK (owner = current_setting('app.actor_id', true))"
                )
            )
        # owner inserts (FORCE RLS applies to owner too unless bypass) -> insert as the probe role instead
    with db_session() as conn:
        conn.execute(text("SET LOCAL ROLE rls_probe_role"))
        for who in ("alice", "bob"):
            conn.execute(text("SELECT set_config('app.actor_id', :w, true)"), {"w": who})
            conn.execute(text("INSERT INTO rls_probe.ht VALUES (:i, now(), :w)"), {"i": 1 if who == "alice" else 2, "w": who})
            conn.execute(text("INSERT INTO rls_probe.reg VALUES (:i, :w)"), {"i": 1 if who == "alice" else 2, "w": who})
    with db_session() as conn:
        conn.execute(text("SET LOCAL ROLE rls_probe_role"))
        conn.execute(text("SELECT set_config('app.actor_id', 'alice', true)"))
        results["hypertable_rows_as_alice"] = conn.execute(text("SELECT string_agg(owner, ',') FROM rls_probe.ht")).scalar()
        results["regular_rows_as_alice"] = conn.execute(text("SELECT string_agg(owner, ',') FROM rls_probe.reg")).scalar()
        try:
            conn.execute(text("SAVEPOINT s"))
            conn.execute(text("INSERT INTO rls_probe.ht VALUES (99, now(), 'bob')"))
            results["cross_owner_insert_blocked"] = False
        except Exception as exc:  # noqa: BLE001
            conn.execute(text("ROLLBACK TO SAVEPOINT s"))
            results["cross_owner_insert_blocked"] = "row-level security" in str(exc)
    with db_session() as conn:
        # context must NOT leak: a new transaction on a (possibly reused) pooled connection
        results["setting_after_commit"] = conn.execute(text("SELECT current_setting('app.actor_id', true)")).scalar()
        results["role_after_commit"] = conn.execute(text("SELECT current_user")).scalar()
        results["pg_version_num"] = conn.execute(text("SHOW server_version_num")).scalar()
    with db_session() as conn:
        conn.execute(text("DROP SCHEMA rls_probe CASCADE"))
        conn.execute(text("REVOKE rls_probe_role FROM current_user"))
        conn.execute(text("DROP ROLE rls_probe_role"))
    for key, value in results.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
