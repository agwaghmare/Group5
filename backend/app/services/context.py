"""Load the customer's current context for contextual lessons.

Banking, credit, and mortgage figures come from the personal-finance dataset.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"


def _num(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    return float(text)


def _read(name: str) -> list[dict[str, str]]:
    path = DATA / name
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@lru_cache(maxsize=1)
def _tables() -> dict[str, list[dict[str, str]]]:
    return {
        "tracker": _read("personal_finance_tracker_dataset.csv"),
    }


@dataclass
class DecisionContext:
    tracker_user_id: int | None = None
    customer_id: str | None = None
    customer: dict | None = None
    account: dict | None = None
    vehicle: dict | None = None
    tracker: dict | None = None
    refi_apr: float | None = None
    refi_term_months: int | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def is_lease(self) -> bool:
        return False

    @property
    def vulnerable(self) -> bool:
        return False


def load_context(customer_id: str | None = None, tracker_user_id: int | None = None, session=None) -> DecisionContext:
    ctx = DecisionContext(customer_id=customer_id, tracker_user_id=tracker_user_id)
    if tracker_user_id is not None:
        from sqlalchemy import select
        from app.orm.access import snapshot_dict
        from app.orm.models import FinanceSnapshot
        if session is None:
            raise ValueError("Personalized context requires an authorized ORM session")
        row = session.scalar(select(FinanceSnapshot).where(FinanceSnapshot.user_id == tracker_user_id).order_by(FinanceSnapshot.date.desc()).limit(1))
        if row:
            ctx.tracker = {key: str(value) if value is not None else None for key, value in snapshot_dict(row).items()}
            ctx.notes.append("Tracker figures are synthetic, loaded through SQLAlchemy.")
        else:
            ctx.notes.append("No tracker rows were found for your account.")
    return ctx


def account_numbers(ctx: DecisionContext) -> dict:
    return {}


def tracker_numbers(ctx: DecisionContext) -> dict:
    if not ctx.tracker:
        return {}
    row = ctx.tracker
    keys = [
        "date",
        "savings_balance",
        "savings_apy",
        "credit_limit_total",
        "credit_utilization",
        "credit_card_apr",
        "home_value",
        "mortgage_balance",
        "mortgage_interest_rate",
        "home_equity",
        "portfolio_value",
    ]
    out: dict = {"source": "personal finance tracker (synthetic)"}
    for key in keys:
        if key == "date":
            out[key] = row[key]
        else:
            out[key] = _num(row[key])
    return out
