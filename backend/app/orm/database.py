"""SQLAlchemy engine and SQLite schema safeguards. No Tiger or Lab Package path."""
import os
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.pool import NullPool, StaticPool

from app.core.config import get_database_url
from app.orm.models import Base


def database_url():
    # Backward-compatible test/development override, not a second staff database.
    override = os.environ.get("STAFF_SQLITE_PATH")
    return "sqlite:///" + str(Path(override).resolve()) if override else get_database_url()


@lru_cache(maxsize=16)
def engine_for(url):
    if not url.startswith("sqlite:"):
        raise RuntimeError("The active local schema requires a SQLite SQLAlchemy URL; cloud/Tiger adapters are retired")
    if url != "sqlite:///:memory:":
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30},
                           poolclass=StaticPool if url == "sqlite:///:memory:" else NullPool)

    @event.listens_for(engine, "connect")
    def sqlite_setup(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")

    Base.metadata.create_all(engine)
    # SQL-level immutability complements API policy; raw UPDATE/DELETE is blocked.
    with engine.begin() as connection:
        for table in ("audit", "runs", "decisions", "case_events", "redemptions", "policies", "benefit_rules", "catalog", "portfolio_assessments", "portfolio_history", "portfolio_assignments"):
            for operation in ("UPDATE", "DELETE"):
                connection.exec_driver_sql(f'CREATE TRIGGER IF NOT EXISTS "immutable_{table}_{operation}" BEFORE {operation} ON "{table}" BEGIN SELECT RAISE(ABORT, \'append-only\'); END')
        connection.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS unique_redemption_request ON redemptions(owner, json_extract(payload, '$.request_id'))")
        connection.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS unique_decision_run ON decisions(json_extract(payload, '$.run_id'))")
    return engine


def get_engine():
    return engine_for(database_url())
