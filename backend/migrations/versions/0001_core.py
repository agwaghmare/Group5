"""PNC-only core schema (finpilot + compliance), hypertables.

Revision ID: 0001
Revises:
"""
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def _run(name: str) -> None:
    op.get_bind().exec_driver_sql((SQL_DIR / name).read_text(encoding="utf-8").replace("%", "%%"))


def upgrade() -> None:
    _run("0001_core.up.sql")


def downgrade() -> None:
    _run("0001_core.down.sql")
