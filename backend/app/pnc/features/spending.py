"""fin.moneymission + SafeSpend, fin.moneyleaks (recurring charges, subscription burden, trends) and fin.rewards.

No merchant field exists in the canonical data and none is invented: recurring items are identified by
category + generic description only.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
from sqlalchemy import Connection, text

from app.pnc.finance import engine as E
from app.pnc.finance.evidence import make_evidence

from .snapshot import Snapshot, last_complete_month_end

D = Decimal


# ---------------------------------------------------------------------------------------------- SafeSpend
def safe_spend(snap: Snapshot, horizon_days: int = 30, goal_contributions: Decimal = D("0")) -> dict:
    """Money that can be spent freely over the horizon after obligations, goals and a buffer."""
    chk = sum((D(str(b)) for b in snap.accounts[snap.accounts.account_type == "checking"].balance), D(0))
    inc, ess = snap.avg("income", 3), snap.avg("essential_spending", 3)
    missing = [n for n, v in (("recent income", inc), ("essential spending", ess)) if v is None]
    if missing:
        return make_evidence("safe_spend", snap.as_of, {"horizon_days": horizon_days}, {"safe_to_spend": None},
                             missing=missing, source_type="pnc_demo_data").model_dump(mode="json")
    end = snap.as_of + timedelta(days=horizon_days)
    due = D(0)
    items = []
    for o in snap.obligations.itertuples() if len(snap.obligations) else []:
        # an obligation falls due once per month on due_day; count each occurrence inside (as_of, end]
        d = date(snap.as_of.year, snap.as_of.month, 1)
        while d <= end:
            try:
                occ = date(d.year, d.month, int(o.due_day or 1))
            except ValueError:
                occ = d
            if snap.as_of < occ <= end:
                due += D(str(o.monthly_amount)); items.append({"kind": o.kind, "amount": str(o.monthly_amount), "due": occ.isoformat()})
            d = date(d.year + (d.month == 12), (d.month % 12) + 1, 1)
    expected_income = inc * D(horizon_days) / D("30.4")
    buffer = ess * D("0.10")
    safe = chk + expected_income - due - goal_contributions - buffer
    ev = make_evidence("safe_spend", snap.as_of, {"checking_balance": chk, "avg_income": inc, "horizon_days": horizon_days,
                                                  "goal_contributions": goal_contributions},
                       {"safe_to_spend": E.money(max(safe, D(0))), "raw_amount": E.money(safe), "per_day": E.money(max(safe, D(0)) / D(horizon_days)),
                        "obligations_due": E.money(due), "expected_income": E.money(expected_income), "buffer": E.money(buffer),
                        "status": "ok" if safe > 0 else "tight", "upcoming_obligations": items},
                       formula_steps=["safe = checking + expected_income - obligations_due - goal_contributions - buffer",
                                      "expected_income = avg monthly income * days / 30.4", "buffer = 10% of average essential spending"],
                       assumptions=["Obligations are the recurring payments on file; unrecognised bills are not included.",
                                    "Income arrives at its recent average rate."], source_type="pnc_demo_data")
    return ev.model_dump(mode="json")


def missions(xray: dict, snap: Snapshot) -> list[dict]:
    """Small, safe, optional missions derived from X-Ray statuses (no pressure, no product pushing)."""
    inc = snap.avg("income", 3) or D(0)
    out, by_id = [], {i["id"]: i for i in xray["indicators"]}
    def add(mid, title, why, target, ind):
        out.append({"mission_id": mid, "title": title, "why": why, "target": target, "linked_indicator": ind,
                    "optional": True, "verify_with": "next month's gold_monthly_cashflow"})
    if by_id["savings_rate"]["status"] in ("risk", "watch"):
        add("save_1pct", f"Move {E.money(inc * D('0.01'))} (1% of monthly income) to savings this month",
            "Savings rate is below the 10% 'ok' threshold; a small automatic transfer builds the habit.", {"amount": str(E.money(inc * D("0.01")))}, "savings_rate")
    if by_id["emergency_fund_months"]["status"] in ("risk", "watch"):
        add("ef_week", "Set aside one week of essential spending as a starter buffer",
            "Emergency fund covers fewer than 3 months of essentials.", {"amount": str(E.money((snap.avg('essential_spending', 3) or D(0)) / D(4)))}, "emergency_fund_months")
    if by_id["credit_utilization"]["status"] in ("risk", "watch"):
        add("util_pay", "Make one extra card payment before the statement closes",
            "Card utilization is above 30%.", {"target_utilization": "0.30"}, "credit_utilization")
    if by_id["cash_flow_surplus_ratio"]["status"] in ("risk", "watch"):
        add("trim_one", "Review one recurring charge and decide whether to keep it",
            "Monthly surplus is thin.", {"count": 1}, "cash_flow_surplus_ratio")
    if not out:
        add("keep_going", "Keep your current habits and check back next month", "Indicators look healthy.", {}, "overall")
    return out


# ---------------------------------------------------------------------------------------------- MoneyLeaks
def _txns(conn: Connection, customer_id: str, as_of: date, months: int = 12) -> pd.DataFrame:
    since = as_of - timedelta(days=int(months * 30.5))
    rows = conn.execute(text(
        "SELECT transaction_id, posted_date, account_id, account_type, category, description, amount, flow_class, transaction_type "
        "FROM pnc_transactions WHERE customer_id = :c AND posted_date > :s AND posted_date <= :a ORDER BY posted_date"),
        {"c": customer_id, "s": since, "a": as_of}).mappings().all()
    df = pd.DataFrame(rows)
    if len(df):
        df["posted_date"] = pd.to_datetime(df["posted_date"])
        df["amount"] = df["amount"].astype(float)
    return df


def recurring_charges(conn: Connection, customer_id: str, as_of: date) -> dict:
    df = _txns(conn, customer_id, as_of)
    found = []
    if len(df):
        ex = df[(df.flow_class == "expense") & (~df.category.str.startswith("debt_payment"))]
        for (cat, desc), g in ex.groupby(["category", "description"]):
            months = g["posted_date"].dt.to_period("M").nunique()
            if months < 6 or len(g) < 6:
                continue
            amts = g["amount"]
            if amts.mean() <= 0 or amts.std(ddof=0) / amts.mean() > 0.15:
                continue
            gaps = g["posted_date"].sort_values().diff().dt.days.dropna()
            if len(gaps) and not (22 <= gaps.median() <= 38):
                continue
            found.append({"category": cat, "description": desc, "monthly_amount": round(float(amts.tail(3).mean()), 2),
                          "occurrences": int(len(g)), "months_observed": int(months),
                          "last_date": g["posted_date"].max().date().isoformat(), "annualized": round(float(amts.mean()) * 12, 2),
                          "detection": "same category+description, >=6 months, amount CV<=15%, ~monthly cadence"})
    found.sort(key=lambda r: -r["monthly_amount"])
    return {"as_of": as_of.isoformat(), "recurring": found, "count": len(found),
            "note": "Merchant names are not part of the data; items are identified by category and generic description only."}


def subscription_burden(conn: Connection, snap: Snapshot) -> dict:
    rec = recurring_charges(conn, snap.customer_id, snap.as_of)
    subs = [r for r in rec["recurring"] if r["category"] == "subscriptions"]
    total = sum((D(str(r["monthly_amount"])) for r in subs), D(0))
    inc = snap.avg("income", 3)
    share = (total / inc) if inc and inc > 0 else None
    return {"as_of": snap.as_of.isoformat(), "subscriptions": subs, "monthly_total": str(E.money(total)),
            "annual_total": str(E.money(total * 12)), "share_of_income": None if share is None else str(E.ratio(share)),
            "status": "n/a" if share is None else "high" if share > D("0.05") else "moderate" if share > D("0.02") else "low",
            "thresholds": {"moderate_above": "0.02", "high_above": "0.05"}}


def spending_trends(snap: Snapshot, conn: Connection) -> dict:
    df = _txns(conn, snap.customer_id, last_complete_month_end(snap.as_of), 7)
    out = []
    if len(df):
        ex = df[(df.flow_class == "expense") & (~df.category.str.startswith("debt_payment"))].copy()
        ex["m"] = ex["posted_date"].dt.to_period("M")
        months = sorted(ex["m"].unique())
        if len(months) >= 6:
            last3, prev3 = months[-3:], months[-6:-3]
            for cat, g in ex.groupby("category"):
                a, b = g[g.m.isin(last3)].amount.sum() / 3, g[g.m.isin(prev3)].amount.sum() / 3
                if b > 0:
                    ch = (a - b) / b
                    out.append({"category": cat, "recent_3m_avg": round(a, 2), "prior_3m_avg": round(b, 2), "change": round(ch, 4),
                                "flag": "rising" if ch > 0.25 and a - b > 20 else "falling" if ch < -0.25 else "steady"})
    out.sort(key=lambda r: -r["change"])
    return {"as_of": snap.as_of.isoformat(), "trends": out, "method": "average monthly spend, last 3 complete months vs the 3 before"}


def possible_duplicates(conn: Connection, customer_id: str, as_of: date) -> list[dict]:
    df = _txns(conn, customer_id, as_of, 3)
    out = []
    if len(df):
        ex = df[(df.flow_class == "expense") & (~df.category.str.startswith("debt_payment")) & (df.category != "rent")]
        for (cat, desc, amt), g in ex.groupby(["category", "description", "amount"]):
            if len(g) > 1 and (g.posted_date.max() - g.posted_date.min()).days <= 3:
                out.append({"category": cat, "description": desc, "amount": float(amt), "dates": [d.date().isoformat() for d in g.posted_date],
                            "note": "Same amount and description within 3 days; may be a duplicate. Informational only."})
    return out


# ---------------------------------------------------------------------------------------------- Rewards
ILLUSTRATIVE_CARDS = [  # illustrative structures, NOT PNC offers
    {"name": "Illustrative flat 1.5% cash back", "rates": {"*": D("0.015")}, "annual_fee": D("0")},
    {"name": "Illustrative 3% groceries / 2% dining / 1% other", "rates": {"groceries": D("0.03"), "dining": D("0.02"), "*": D("0.01")}, "annual_fee": D("0")},
    {"name": "Illustrative 4% travel & dining / 1% other ($95 fee)", "rates": {"travel": D("0.04"), "dining": D("0.04"), "*": D("0.01")}, "annual_fee": D("95")},
]


def rewards_compare(conn: Connection, snap: Snapshot) -> dict:
    df = _txns(conn, snap.customer_id, snap.as_of, 12)
    cards = snap.accounts[snap.accounts.account_type == "credit_card"]
    carry = sum((D(str(b)) for b in cards.balance), D(0))
    apr = max([D(str(a)) for a in cards.apr_pct], default=D(0)) / D(100)
    spend = {}
    if len(df):
        ex = df[(df.flow_class == "expense") & (~df.category.str.startswith("debt_payment")) & (df.category != "rent")]
        spend = {k: D(str(round(v, 2))) for k, v in ex.groupby("category")["amount"].sum().items()}
    total = sum(spend.values(), D(0))
    rows = []
    for c in ILLUSTRATIVE_CARDS:
        earned = sum((v * c["rates"].get(k, c["rates"]["*"]) for k, v in spend.items()), D(0))
        rows.append({"card": c["name"], "estimated_annual_rewards": str(E.money(earned)), "annual_fee": str(c["annual_fee"]),
                     "net_annual_value": str(E.money(earned - c["annual_fee"]))})
    rows.sort(key=lambda r: -D(r["net_annual_value"]))
    interest = carry * apr
    return {"as_of": snap.as_of.isoformat(), "annual_spend_basis": str(E.money(total)), "options": rows,
            "carried_balance": str(E.money(carry)), "approx_annual_interest_on_carried_balance": str(E.money(interest)),
            "caution": ("Rewards are worth less than the interest you may pay on a carried balance." if interest > 0 and rows and interest > D(rows[0]["net_annual_value"]) else None),
            "disclaimer": "Illustrative reward structures for comparison only; not PNC products, offers, or advice."}
