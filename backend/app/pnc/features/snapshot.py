"""Point-in-time customer snapshot: nothing dated after ``as_of`` is ever read (no leakage).

All queries run on the caller's connection, so when that connection is a customer-role session, RLS limits every
row to the authenticated customer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
from sqlalchemy import Connection, text

from app.pnc.errors import NotFound

ASSET_TYPES = {"checking", "savings", "cd", "ira"}
LIABILITY_TYPES = {"credit_card", "auto_loan", "personal_loan", "mortgage"}
LIQUID_TYPES = {"checking", "savings"}


def _d(x) -> Decimal:
    return Decimal(str(x))


def last_complete_month_end(as_of: date) -> date:
    """Latest month-end <= as_of (months after it are partial and excluded from monthly aggregates)."""
    nxt = date(as_of.year + (as_of.month == 12), (as_of.month % 12) + 1, 1)
    return as_of if nxt - timedelta(days=1) == as_of else date(as_of.year, as_of.month, 1) - timedelta(days=1)


@dataclass
class Snapshot:
    customer_id: str
    as_of: date
    profile: dict
    accounts: pd.DataFrame
    monthly: pd.DataFrame            # complete months only, ascending
    obligations: pd.DataFrame
    balance_history: pd.DataFrame    # month-end balances per account <= as_of
    missing: list[str] = field(default_factory=list)

    # ---- derived helpers (Decimal)
    def sum_balance(self, types: set[str]) -> Decimal:
        sel = self.accounts[self.accounts.account_type.isin(types)]
        return sum((_d(b) for b in sel.balance), Decimal(0))

    @property
    def liquid(self) -> Decimal:
        return self.sum_balance(LIQUID_TYPES)

    @property
    def assets(self) -> Decimal:
        return self.sum_balance(ASSET_TYPES)

    @property
    def liabilities(self) -> Decimal:
        return self.sum_balance(LIABILITY_TYPES)

    def recent(self, col: str, months: int) -> list[Decimal]:
        return [_d(v) for v in self.monthly[col].tail(months)]

    def avg(self, col: str, months: int) -> Decimal | None:
        vals = self.recent(col, months)
        return sum(vals, Decimal(0)) / len(vals) if vals else None


def load_snapshot(conn: Connection, customer_id: str, as_of: date) -> Snapshot:
    me = last_complete_month_end(as_of)
    prof = conn.execute(text(
        "SELECT customer_id, display_name, age, city, pay_frequency, annual_income, income_sources_count, credit_score "
        "FROM pnc_customers WHERE customer_id = :c"), {"c": customer_id}).mappings().first()
    if prof is None:
        raise NotFound("customer not found or not visible")
    accounts = pd.DataFrame(conn.execute(text("""
        SELECT a.account_id, a.account_type, a.name, a.apr_pct, a.apy_pct, a.credit_limit, a.required_monthly_payment,
               a.opened_date,
               coalesce((SELECT t.balance_after FROM pnc_transactions t WHERE t.account_id = a.account_id
                          AND t.posted_date <= :as_of ORDER BY t.posted_date DESC, t.transaction_id DESC LIMIT 1),
                        (SELECT m.opening_balance FROM pnc_monthly_statements m WHERE m.account_id = a.account_id
                          ORDER BY m.statement_month LIMIT 1)) AS balance
          FROM pnc_accounts a WHERE a.customer_id = :c AND a.opened_date <= :as_of ORDER BY a.account_id"""),
        {"c": customer_id, "as_of": as_of}).mappings().all())
    monthly = pd.DataFrame(conn.execute(text(
        "SELECT * FROM gold_monthly_cashflow WHERE customer_id = :c AND month <= :me "
        "AND (month + INTERVAL '1 month' - INTERVAL '1 day')::date <= :me ORDER BY month"),
        {"c": customer_id, "me": me}).mappings().all())
    obligations = pd.DataFrame(conn.execute(text(
        "SELECT obligation_id, account_id, kind, monthly_amount, due_day, origin FROM pnc_recurring_obligations WHERE customer_id = :c"),
        {"c": customer_id}).mappings().all())
    bh = pd.DataFrame(conn.execute(text(
        "SELECT account_id, as_of, account_type, balance FROM pnc_balance_history WHERE customer_id = :c AND as_of <= :a ORDER BY as_of"),
        {"c": customer_id, "a": as_of}).mappings().all())
    missing = []
    if monthly.empty:
        missing.append("monthly cash-flow history before as_of")
    if accounts.empty:
        missing.append("accounts open at as_of")
    return Snapshot(customer_id, as_of, dict(prof), accounts, monthly, obligations, bh, missing)


def net_worth_series(snap: Snapshot) -> pd.Series:
    """Net worth at each month-end (assets - liabilities) from balance history."""
    if snap.balance_history.empty:
        return pd.Series(dtype=float)
    df = snap.balance_history.copy()
    df["signed"] = df.apply(lambda r: float(r.balance) * (1 if r.account_type in ASSET_TYPES else -1), axis=1)
    return df.groupby("as_of")["signed"].sum()
