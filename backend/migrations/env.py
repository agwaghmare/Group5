"""Alembic environment. Migrations are raw SQL so TimescaleDB/RLS DDL stays explicit and reviewable."""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The version table lives in public so downgrading 0001 (which drops schema finpilot) is safe.
VERSION_TABLE = "finpilot_alembic_version"


def run_migrations_offline() -> None:
    context.configure(url=get_database_url(), literal_binds=True, version_table=VERSION_TABLE)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, version_table=VERSION_TABLE, version_table_schema="public")
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
