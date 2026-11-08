"""DB roles, RLS, masked views, purpose-gated functions, append-only triggers.

Revision ID: 0002
Revises: 0001
"""
from pathlib import Path

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def _run(name: str) -> None:
    op.get_bind().exec_driver_sql((SQL_DIR / name).read_text(encoding="utf-8").replace("%", "%%"))


def upgrade() -> None:
    _run("0002_security.up.sql")


def downgrade() -> None:
    _run("0002_security.down.sql")
