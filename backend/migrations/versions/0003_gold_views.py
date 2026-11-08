"""Gold views (security_invoker) over the transaction ledger.

Revision ID: 0003
Revises: 0002
"""
from pathlib import Path

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def _run(name: str) -> None:
    op.get_bind().exec_driver_sql((SQL_DIR / name).read_text(encoding="utf-8").replace("%", "%%"))


def upgrade() -> None:
    _run("0003_gold_views.up.sql")


def downgrade() -> None:
    _run("0003_gold_views.down.sql")
