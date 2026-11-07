"""Load the customer's current contract for contextual lessons.

Vehicle and TFS figures come from the Toyota next-move pack.
Banking, credit, and mortgage figures for a tracker user come from the
personal-finance dataset, which has no vehicle columns.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
BUYOUT_FEE = 350.0


def _num(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    return float(text)


def _read(name: str) -> list[dict[str, str]]:
    path = DATA / name
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@lru_cache(maxsize=1)
def _tables() -> dict[str, list[dict[str, str]]]:
    return {
        "customers": _read("customers.csv"),
        "accounts": _read("accounts.csv"),
        "vehicles": _read("vehicles.csv"),
        "rates": _read("rate_sheet.csv"),
        "tracker": _read("personal_finance_tracker_dataset.csv"),
    }


@dataclass
class DecisionContext:
    customer_id: str | None = None
    tracker_user_id: int | None = None
    customer: dict | None = None
    account: dict | None = None
    vehicle: dict | None = None
    tracker: dict | None = None
    refi_apr: float | None = None
    refi_term_months: int | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def is_lease(self) -> bool:
        return bool(self.account and self.account.get("contract_type") == "lease")

    @property
    def vulnerable(self) -> bool:
        return bool(self.customer and str(self.customer.get("vulnerable_flag", "")).upper() == "Y")


def _pick_refi(tier: str | None, months_remaining: int | None) -> tuple[float | None, int | None]:
    if not tier or not months_remaining:
        return None, None
    rows = []
    for row in _tables()["rates"]:
        if row["credit_tier"] != tier:
            continue
        rows.append((int(row["term_months"]), float(row["refinance_apr"])))
    if not rows:
        return None, None
    longer = [row for row in rows if row[0] >= months_remaining]
    term, apr = min(longer, key=lambda item: item[0]) if longer else max(rows, key=lambda item: item[0])
    return apr, term


def load_context(customer_id: str | None = None, tracker_user_id: int | None = None) -> DecisionContext:
    tables = _tables()
    ctx = DecisionContext(customer_id=customer_id, tracker_user_id=tracker_user_id)
    if customer_id:
        ctx.customer = next((row for row in tables["customers"] if row["customer_id"] == customer_id), None)
        ctx.account = next((row for row in tables["accounts"] if row["customer_id"] == customer_id), None)
        ctx.vehicle = next((row for row in tables["vehicles"] if row["customer_id"] == customer_id), None)
        if ctx.customer is None or ctx.account is None:
            ctx.notes.append(f"No Toyota contract was found for {customer_id}.")
        elif ctx.customer:
            months = _num(ctx.account.get("months_remaining"))
            apr, term = _pick_refi(ctx.customer.get("credit_tier_now"), int(months) if months else None)
            ctx.refi_apr = apr
            ctx.refi_term_months = term
            ctx.notes.append("Toyota figures are synthetic hackathon data, not a live offer.")
            if ctx.vulnerable:
                ctx.notes.append("This is education, not an offer. A person can walk through the numbers with you.")
    if tracker_user_id is not None:
        rows = [row for row in tables["tracker"] if int(float(row["user_id"])) == int(tracker_user_id)]
        if rows:
            ctx.tracker = max(rows, key=lambda row: row["date"])
            ctx.notes.append("Tracker figures are synthetic and are not a Toyota contract.")
        else:
            ctx.notes.append(f"No tracker rows were found for user {tracker_user_id}.")
    return ctx


def account_numbers(ctx: DecisionContext) -> dict:
    if not ctx.account:
        return {}
    account = ctx.account
    vehicle = ctx.vehicle or {}
    numbers = {
        "contract_type": account.get("contract_type"),
        "apr": _num(account.get("apr")),
        "money_factor": _num(account.get("money_factor")),
        "monthly_payment": _num(account.get("monthly_payment")),
        "current_balance": _num(account.get("current_balance")),
        "payoff_quote": _num(account.get("payoff_quote")),
        "residual_value": _num(account.get("residual_value")),
        "amount_financed": _num(account.get("amount_financed")),
        "months_remaining": _num(account.get("months_remaining")),
        "term_months": _num(account.get("term_months")),
        "est_equity": _num(account.get("est_equity")),
        "mileage_allowance_total": _num(account.get("mileage_allowance_total")),
        "missed_payments_12m": _num(account.get("missed_payments_12m")),
        "vehicle": f"{vehicle.get('model_year', '')} {vehicle.get('model', '')}".strip(),
        "purchase_price": _num(vehicle.get("purchase_price_or_msrp")),
        "market_value": _num(vehicle.get("est_market_value_now")),
        "odometer": _num(vehicle.get("odometer_now")),
        "refi_apr_from_sheet": ctx.refi_apr,
        "refi_term_on_sheet": ctx.refi_term_months,
        "credit_tier_now": (ctx.customer or {}).get("credit_tier_now"),
        "buyout_fee_assumption": BUYOUT_FEE,
        "source": "Toyota next-move data pack (synthetic)",
    }
    return {key: value for key, value in numbers.items() if value is not None}


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
