"""SQLAlchemy engine and transaction-scoped security context.

Every request runs inside one transaction. Inside it we `SET LOCAL ROLE` to a
least-privilege database role and set transaction-local `app.*` settings that the
row-level-security policies read. `SET LOCAL` and `set_config(..., true)` are
discarded at COMMIT/ROLLBACK, so pooled connections cannot leak identity between
requests.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterator

from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import get_database_url, get_settings

ORG = "pnc"

ROLES = (
    "customer",
    "credit_analyst",
    "service_specialist",
    "marketing_analyst",
    "portfolio_manager",
    "compliance_analyst",
    "auditor",
    "benefits_admin",
)
DB_ROLE_PREFIX = "app_"


@dataclass(frozen=True)
class SessionContext:
    """Identity for one request. Always derived from the authenticated session."""

    role: str
    actor_id: str
    org: str = ORG
    customer_id: str | None = None
    employee_id: str | None = None
    grant_id: str | None = None
    break_glass: bool = False
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"unknown role {self.role!r}")

    @property
    def db_role(self) -> str:
        return DB_ROLE_PREFIX + self.role


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    if get_database_url().startswith("sqlite:"):
        from app.orm.database import get_engine as orm_engine
        return orm_engine()
    return create_engine(
        get_database_url(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=900,
        connect_args={"options": f"-c search_path={settings.db_schema},public"},
    )


def _apply_context(conn: Connection, ctx: SessionContext) -> None:
    if conn.dialect.name == "sqlite":
        raise RuntimeError("Legacy PostgreSQL role queries are retired; use the scoped ORM services")
    # Role names cannot be bound as parameters; ctx.db_role is whitelisted in __post_init__.
    conn.execute(text(f"SET LOCAL ROLE {ctx.db_role}"))
    settings = {
        "app.role": ctx.role,
        "app.org": ctx.org,
        "app.actor_id": ctx.actor_id,
        "app.customer_id": ctx.customer_id or "",
        "app.employee_id": ctx.employee_id or "",
        "app.grant_id": ctx.grant_id or "",
        "app.break_glass": "true" if ctx.break_glass else "false",
        "app.request_id": ctx.request_id,
    }
    for key, value in settings.items():
        conn.execute(text("SELECT set_config(:k, :v, true)"), {"k": key, "v": value})


@contextmanager
def db_session(ctx: SessionContext | None = None) -> Iterator[Connection]:
    """Open a transaction. With `ctx`, run as the least-privilege role for that identity.

    Without `ctx` the connection runs as the owner (migrations, pipelines, seeds,
    background jobs). Never expose the owner path to an HTTP handler.
    """
    with get_engine().begin() as conn:
        if ctx is not None:
            _apply_context(conn, ctx)
        yield conn


def dispose_engine() -> None:
    if get_engine.cache_info().currsize:
        get_engine().dispose()
        get_engine.cache_clear()


def ping() -> dict:
    with db_session() as conn:
        row = conn.execute(text("SELECT current_user, version()")).one()
    return {"user": row[0], "version": row[1]}
