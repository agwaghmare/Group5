"""Fix ambiguous column in compliance.fairness_report.

Revision ID: 0004
Revises: 0003
"""
from pathlib import Path

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def _run(name: str) -> None:
    op.get_bind().exec_driver_sql((SQL_DIR / name).read_text(encoding="utf-8").replace("%", "%%"))


def upgrade() -> None:
    _run("0004_fairness_fix.up.sql")


def downgrade() -> None:
    _run("0004_fairness_fix.down.sql")
