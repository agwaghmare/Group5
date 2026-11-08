"""Lab_Package-compatible DEMO data generator (NOT the sponsor data).

The sponsor ``Lab_Package`` / ``wellness`` toolkit is not present in this repository, so this module writes a
separately labeled substitute that follows the documented contract:

* 30 customers C001..C030, 196 accounts across 8 types, 24 months 2024-11-01..2026-10-31,
  one statement per account-month (4,704).
* snapshot seed 20261107 (customers/accounts), history seed 20261108 (transactions).
* Accounting conventions (see Skill.md section 5): positive balances for assets and liabilities, paired
  internal transfers, debt payments counted once on the checking leg, external cash-management flows are
  artificial and excluded from income/spending, interest postings are non-cash, no merchant field.

Every row carries ``source_type = synthetic_demo_substitute``. Money is generated in integer cents.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SOURCE_TYPE = "synthetic_demo_substitute"
SNAPSHOT_SEED = 20261107
HISTORY_SEED = 20261108
START = date(2024, 11, 1)
END = date(2026, 10, 31)
N_CUSTOMERS = 30
N_ACCOUNTS = 196
TYPE_COUNTS = {
    "checking": 30, "savings": 30, "cd": 18, "ira": 22,
    "credit_card": 42, "auto_loan": 20, "personal_loan": 16, "mortgage": 18,
}
LIABILITIES = {"credit_card", "auto_loan", "personal_loan", "mortgage"}
CITIES = ["Pittsburgh", "Philadelphia", "Cleveland", "Columbus", "Cincinnati", "Louisville",
          "Baltimore", "Charlotte", "Atlanta", "Chicago", "Detroit", "St. Louis"]
FIRST = ["Alex", "Blake", "Casey", "Drew", "Emery", "Finley", "Gray", "Harper", "Indy", "Jules",
         "Kai", "Lane", "Morgan", "Noel", "Oakley", "Parker", "Quinn", "Reese", "Sage", "Tatum"]
LAST = ["Adler", "Brooks", "Carver", "Dalton", "Ellis", "Foster", "Gallo", "Hayes", "Irwin", "Jensen"]
ARCHETYPES = ["stable", "stretched", "saver", "variable_income", "debt_heavy"]
ARCH_WEIGHTS = [0.35, 0.20, 0.15, 0.15, 0.15]
ARCH_PARAMS = {  # essential share, savings transfer share, card payoff, target = consumption+debt share of net income
    "stable":          dict(ess=0.50, disc=0.13, save=0.08, payoff=0.85, target=0.88),
    "stretched":       dict(ess=0.58, disc=0.22, save=0.02, payoff=0.35, target=0.985),
    "saver":           dict(ess=0.42, disc=0.10, save=0.18, payoff=1.00, target=0.70),
    "variable_income": dict(ess=0.48, disc=0.15, save=0.06, payoff=0.60, target=0.90),
    "debt_heavy":      dict(ess=0.45, disc=0.14, save=0.03, payoff=0.40, target=0.96),
}
DISC_CATS = [("groceries", 0.30), ("dining", 0.16), ("fuel", 0.10), ("shopping", 0.18),
             ("entertainment", 0.09), ("healthcare", 0.07), ("travel", 0.06), ("education", 0.04)]


def cents(x: float) -> int:
    return int(round(x * 100))


def amort_payment(principal: float, apr_pct: float, n: int) -> float:
    r = apr_pct / 1200.0
    return principal / n if r == 0 else principal * r / (1 - (1 + r) ** -n)


def _month_starts() -> list[date]:
    out, y, m = [], START.year, START.month
    while date(y, m, 1) <= END:
        out.append(date(y, m, 1))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def _month_end(d: date) -> date:
    nxt = date(d.year + (d.month == 12), (d.month % 12) + 1, 1)
    return nxt - timedelta(days=1)


@dataclass
class Acct:
    account_id: str
    customer_id: str
    account_type: str
    name: str
    opened_date: date
    opening_cents: int
    apy_pct: float | None = None
    apr_pct: float | None = None
    credit_limit: float | None = None
    original_principal: float | None = None
    term_months: int | None = None
    payment: float | None = None
    maturity_date: date | None = None
    balance_c: int = 0
    month_open_c: int = 0
    events: list = field(default_factory=list)


def _assign_types(rng: np.random.Generator, incomes: np.ndarray) -> dict[str, list[str]]:
    """Distribute exactly TYPE_COUNTS accounts over customers (checking+savings for all)."""
    ids = [f"C{i + 1:03d}" for i in range(N_CUSTOMERS)]
    held: dict[str, list[str]] = {c: ["checking", "savings"] for c in ids}
    w = incomes / incomes.sum()

    def pick(n: int, weights: np.ndarray | None) -> list[str]:
        idx = rng.choice(N_CUSTOMERS, size=n, replace=False, p=weights)
        return [ids[i] for i in sorted(idx)]

    for c in pick(TYPE_COUNTS["cd"], w): held[c].append("cd")
    for c in pick(TYPE_COUNTS["ira"], w): held[c].append("ira")
    for c in pick(TYPE_COUNTS["mortgage"], w): held[c].append("mortgage")
    for c in pick(TYPE_COUNTS["auto_loan"], None): held[c].append("auto_loan")
    for c in pick(TYPE_COUNTS["personal_loan"], None): held[c].append("personal_loan")
    for c in ids: held[c].append("credit_card")                         # 30 first cards
    for c in pick(TYPE_COUNTS["credit_card"] - N_CUSTOMERS, w): held[c].append("credit_card")  # 12 second cards
    return held


def generate(out_dir: Path) -> dict:
    """Write the demo package to ``out_dir`` and return the manifest dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    snap = np.random.default_rng(SNAPSHOT_SEED)
    hist = np.random.default_rng(HISTORY_SEED)

    # ------------------------------------------------------------------ customers (snapshot seed)
    incomes = np.clip(snap.lognormal(mean=11.05, sigma=0.45, size=N_CUSTOMERS), 28000, 230000).round(-2)
    archetypes = snap.choice(ARCHETYPES, size=N_CUSTOMERS, p=ARCH_WEIGHTS)
    freqs = snap.choice(["weekly", "biweekly", "semimonthly", "monthly"], size=N_CUSTOMERS, p=[0.1, 0.4, 0.35, 0.15])
    ages = snap.integers(23, 71, size=N_CUSTOMERS)
    scores = np.clip(snap.normal(705, 65, size=N_CUSTOMERS), 540, 830).round().astype(int)
    consent = snap.random(N_CUSTOMERS) < 0.7
    vulnerable = snap.random(N_CUSTOMERS) < 0.12
    channels = snap.choice(["email", "sms", "phone", "mail"], size=N_CUSTOMERS, p=[0.5, 0.25, 0.15, 0.1])
    customers = []
    for i in range(N_CUSTOMERS):
        a = str(archetypes[i])
        p = ARCH_PARAMS[a]
        customers.append(dict(
            customer_id=f"C{i + 1:03d}",
            display_name=f"{FIRST[i % len(FIRST)]} {LAST[(i * 3) % len(LAST)]}",
            age=int(ages[i]), city=CITIES[int(snap.integers(0, len(CITIES)))],
            pay_frequency=str(freqs[i]), annual_income=float(incomes[i]),
            income_sources_count=2 if (a == "variable_income" or snap.random() < 0.15) else 1,
            credit_score=int(scores[i]), essential_spending_ratio=p["ess"], savings_rate_assumption=p["save"],
            marketing_consent=bool(consent[i]), vulnerable_flag=bool(vulnerable[i]),
            preferred_channel=str(channels[i]), source_type=SOURCE_TYPE,
        ))
    held = _assign_types(snap, incomes)

    # ------------------------------------------------------------------ accounts (snapshot seed)
    accounts: list[Acct] = []
    seq = 0
    for i, cust in enumerate(customers):
        cid, inc, arch = cust["customer_id"], cust["annual_income"], str(archetypes[i])
        net_m = inc * 0.78 / 12
        for typ in held[cid]:
            seq += 1
            aid = f"A{seq:04d}"
            if typ == "checking":
                a = Acct(aid, cid, typ, "PNC Checking", date(2018, 1, 1) + timedelta(days=int(snap.integers(0, 2000))),
                         cents(net_m * snap.uniform(1.0, 2.5)))
            elif typ == "savings":
                a = Acct(aid, cid, typ, "PNC Savings", date(2019, 1, 1) + timedelta(days=int(snap.integers(0, 1800))),
                         cents(net_m * snap.uniform(0.5, 6.0) * (1.6 if arch == "saver" else 0.5 if arch == "stretched" else 1.0)),
                         apy_pct=round(float(snap.uniform(0.4, 3.9)), 2))
            elif typ == "cd":
                bal = round(float(snap.uniform(3000, 40000)), -2)
                term = int(snap.choice([12, 24, 36, 60]))
                opened = date(2024, 1, 1) + timedelta(days=int(snap.integers(0, 300)))
                a = Acct(aid, cid, typ, f"PNC CD {term}m", opened, cents(bal), apy_pct=round(float(snap.uniform(3.5, 5.0)), 2),
                         original_principal=bal, term_months=term,
                         maturity_date=date(opened.year + (opened.month - 1 + term) // 12, (opened.month - 1 + term) % 12 + 1, 1))
            elif typ == "ira":
                a = Acct(aid, cid, typ, "PNC IRA", date(2015, 1, 1) + timedelta(days=int(snap.integers(0, 3000))),
                         cents(inc * snap.uniform(0.2, 2.5) * (ages[i] / 45)))
            elif typ == "credit_card":
                limit = round(float(snap.choice([3000, 5000, 8000, 12000, 20000])) * (inc / 70000) ** 0.4, -2)
                util = float(snap.uniform(0.35, 0.80)) if arch in ("stretched", "debt_heavy") else float(snap.uniform(0.02, 0.25))
                a = Acct(aid, cid, typ, "PNC Cash Rewards Card", date(2016, 1, 1) + timedelta(days=int(snap.integers(0, 3000))),
                         cents(limit * util), apr_pct=round(float(snap.uniform(17, 28.5)), 2), credit_limit=limit)
            else:
                spec = {"auto_loan": (0.06, 0.10, 48, 72, 4.2, 9.5, 1, "PNC Auto Loan"),
                        "personal_loan": (0.03, 0.05, 24, 60, 8.0, 17.0, 1, "PNC Personal Loan"),
                        "mortgage": (0.18, 0.26, 180, 360, 4.5, 7.4, 1, "PNC Mortgage")}[typ]
                term = int(snap.choice([spec[2], (spec[2] + spec[3]) // 2, spec[3]])) if typ != "mortgage" else int(snap.choice([180, 360]))
                apr = round(float(snap.uniform(spec[4], spec[5])), 2)
                # size the loan so the monthly payment is a bounded share of net income (keeps the demo solvent)
                target_pay = net_m * float(snap.uniform(spec[0], spec[1]))
                principal = round(target_pay / amort_payment(1.0, apr, term), -2)
                pay = amort_payment(principal, apr, term)
                paid = int(snap.integers(1, max(2, min(term - 26, 60))))   # payments made before the window
                r = apr / 1200
                bal = principal * (1 + r) ** paid - pay * (((1 + r) ** paid - 1) / r)
                opened = date(START.year, START.month, 1) - timedelta(days=30 * paid)
                a = Acct(aid, cid, typ, spec[7], opened, cents(bal), apr_pct=apr, original_principal=principal,
                         term_months=term, payment=round(pay, 2))
            a.balance_c = a.month_open_c = a.opening_cents
            accounts.append(a)
    assert len(accounts) == N_ACCOUNTS, len(accounts)
    by_cust: dict[str, dict[str, list[Acct]]] = {}
    for a in accounts:
        by_cust.setdefault(a.customer_id, {}).setdefault(a.account_type, []).append(a)

    # ------------------------------------------------------------------ history (history seed)
    ledger: list[dict] = []   # rows: account_id, posted_date, order, ...
    order = 0
    transfer_no = 0

    def post(acct: Acct, d: date, ttype: str, category: str, desc: str, amount_c: int, sign: int,
             flow: str, transfer_id: str | None = None) -> None:
        nonlocal order
        order += 1
        acct.balance_c += sign * amount_c
        ledger.append(dict(account_id=acct.account_id, customer_id=acct.customer_id, account_type=acct.account_type,
                           posted_date=d, order=order, transaction_type=ttype, category=category, description=desc,
                           amount=amount_c / 100, balance_change=sign * amount_c / 100, balance_after=acct.balance_c / 100,
                           flow_class=flow, transfer_id=transfer_id, source_type=SOURCE_TYPE))

    def pair(src: Acct, dst: Acct, d: date, amount_c: int, category: str, desc: str) -> None:
        """Paired internal transfer (asset -> asset)."""
        nonlocal transfer_no
        transfer_no += 1
        tid = f"X{transfer_no:06d}"
        post(src, d, "transfer_out", category, desc, amount_c, -1, "internal_transfer", tid)
        post(dst, d, "transfer_in", category, desc, amount_c, +1, "internal_transfer", tid)

    external_customers = set(hist.choice([c["customer_id"] for c in customers], size=6, replace=False))
    months = _month_starts()
    for mi, ms in enumerate(months):
        me = _month_end(ms)
        for a in accounts:
            a.month_open_c = a.balance_c
        for cust in customers:
            cid, arch = cust["customer_id"], str(archetypes[int(cid[1:]) - 1])
            P = ARCH_PARAMS[arch]
            hold = by_cust[cid]
            chk, sav = hold["checking"][0], hold["savings"][0]
            net_m = cust["annual_income"] * 0.78 / 12
            factor = float(np.clip(hist.lognormal(0, 0.22), 0.55, 1.6)) if arch == "variable_income" else 1.0
            plan: list[tuple[int, int, str, tuple]] = []   # (day, tiebreak, kind, args)

            # payroll
            freq = cust["pay_frequency"]
            if freq == "monthly": days = [28]
            elif freq == "semimonthly": days = [14, 28]
            elif freq == "biweekly": days = [7, 21] if mi % 2 == 0 else [14, 28]
            else: days = [7, 14, 21, 28]
            for d in days:
                plan.append((d, 1, "payroll", (cents(net_m * factor / len(days)),)))
            if cust["income_sources_count"] > 1:
                plan.append((int(hist.integers(3, 25)), 2, "side_income", (cents(net_m * 0.12 * float(hist.uniform(0.5, 1.5))),)))
            # housing
            if "mortgage" in hold:
                plan.append((1, 3, "debt_pay", (hold["mortgage"][0],)))
            else:
                plan.append((1, 3, "rent", (cents(net_m * 0.30 * (1 + 0.03 * (mi // 12))),)))
            # other loans
            for typ in ("auto_loan", "personal_loan"):
                if typ in hold:
                    plan.append((int(5 + 3 * (typ == "personal_loan")), 3, "debt_pay", (hold[typ][0],)))
            # recurring bills (same amount each month; generic descriptions only)
            for k, (cat, share) in enumerate([("utilities", 0.045), ("insurance", 0.04), ("telecom", 0.018)]):
                plan.append((10 + k * 4, 4, "bill", (cat, cents(net_m * share * (0.9 + 0.02 * (int(cid[1:]) % 10))))))
            for k in range(2 + int(cid[1:]) % 3):
                plan.append((12 + k * 5, 4, "subscription", (k, cents(6 + 4.5 * ((int(cid[1:]) + k) % 6)))))
            # discretionary / grocery card+debit spending
            # discretionary + grocery budget fills the gap between fixed outflows and the archetype's spending target
            loans_m = sum(a.payment for t in ("mortgage", "auto_loan", "personal_loan") for a in hold.get(t, []) if a.balance_c > 0)
            housing_m = 0.0 if "mortgage" in hold else net_m * 0.30 * (1 + 0.03 * (mi // 12))
            fixed_m = loans_m + housing_m + net_m * (0.045 + 0.04 + 0.018) + 3 * 20.0
            budget = max(net_m * P["target"] - fixed_m, net_m * 0.10)
            n_tx = int(hist.integers(7, 12))
            weights = np.array([w for _, w in DISC_CATS]); weights = weights / weights.sum()
            cats = hist.choice(len(DISC_CATS), size=n_tx, p=weights)
            raw = hist.lognormal(0, 0.55, size=n_tx)
            amts = raw / raw.sum() * max(budget, 50)
            for c_i, amt in zip(cats, amts):
                use_card = bool(hist.random() < 0.55)
                plan.append((int(hist.integers(2, 28)), 5, "spend", (DISC_CATS[c_i][0], cents(float(amt)), use_card)))
            # savings / retirement contributions
            plan.append((int(hist.integers(2, 5)), 6, "to_savings", (cents(net_m * P["save"]),)))
            if "ira" in hold:
                plan.append((15, 6, "to_ira", (cents(min(net_m * 0.05, 541.0)),)))
            # card payments
            for card in hold.get("credit_card", []):
                plan.append((20, 7, "card_pay", (card, P["payoff"])))
            # artificial external cash-management flows
            if cid in external_customers:
                plan.append((int(hist.integers(5, 25)), 8, "ext", (cents(float(hist.uniform(100, 600))), bool(hist.random() < 0.5))))

            plan.sort(key=lambda t: (t[0], t[1]))
            for day, _, kind, args in plan:
                d = date(ms.year, ms.month, min(day, 28))
                if kind in ("payroll", "side_income"):
                    post(chk, d, "deposit", "payroll" if kind == "payroll" else "other_income",
                         "Direct deposit" if kind == "payroll" else "Other deposit", args[0], +1, "income")
                    continue
                if kind == "ext":
                    amt, incoming = args
                    post(chk, d, "external_transfer", "external_cash_management",
                         "External cash management (artificial)", amt, +1 if incoming else -1, "external_transfer")
                    continue
                if kind == "to_savings":
                    if chk.balance_c - args[0] > cents(net_m * 0.3):
                        pair(chk, sav, d, args[0], "savings_transfer", "Transfer to savings")
                    continue
                if kind == "to_ira":
                    ira = hold["ira"][0]
                    if chk.balance_c - args[0] > cents(net_m * 0.3):
                        pair(chk, ira, d, args[0], "retirement_contribution", "IRA contribution")
                    continue

                # outflows from checking: top up from savings if short
                def ensure(needed_c: int) -> None:
                    if chk.balance_c < needed_c and sav.balance_c > 0:
                        move = min(sav.balance_c, needed_c - chk.balance_c + cents(net_m * 0.1))
                        pair(sav, chk, d, move, "savings_transfer", "Transfer from savings")

                if kind == "rent":
                    ensure(args[0]); post(chk, d, "bill_payment", "rent", "Rent payment", args[0], -1, "expense")
                elif kind == "bill":
                    ensure(args[1]); post(chk, d, "bill_payment", args[0], f"Recurring bill - {args[0]}", args[1], -1, "expense")
                elif kind == "subscription":
                    ensure(args[1]); post(chk, d, "bill_payment", "subscriptions", f"Recurring subscription {args[0] + 1}", args[1], -1, "expense")
                elif kind == "debt_pay":
                    loan: Acct = args[0]
                    pay_c = min(cents(loan.payment), loan.balance_c)
                    if pay_c <= 0:
                        continue
                    ensure(pay_c)
                    transfer_no += 1
                    tid = f"X{transfer_no:06d}"
                    post(chk, d, "loan_payment", f"debt_payment_{loan.account_type}", f"Payment to {loan.name}", pay_c, -1, "expense", tid)
                    post(loan, d, "loan_payment_applied", "payment_received", f"Payment applied to {loan.name}", pay_c, -1, "non_cash", tid)
                elif kind == "card_pay":
                    card: Acct = args[0]
                    due_c = int(card.balance_c * args[1])
                    if due_c <= 0:
                        continue
                    due_c = max(due_c, min(card.balance_c, cents(25)))
                    if arch in ("stretched", "debt_heavy") and chk.balance_c < due_c:
                        due_c = max(min(card.balance_c, cents(25)), chk.balance_c // 2)
                    if chk.balance_c < due_c:
                        ensure(due_c)
                    if chk.balance_c < due_c:
                        continue
                    transfer_no += 1
                    tid = f"X{transfer_no:06d}"
                    post(chk, d, "card_payment", "debt_payment_credit_card", f"Payment to {card.name}", due_c, -1, "expense", tid)
                    post(card, d, "payment_applied", "payment_received", "Card payment received", due_c, -1, "non_cash", tid)
                elif kind == "spend":
                    cat, amt, use_card = args
                    if use_card and hold.get("credit_card"):
                        card = hold["credit_card"][int(hist.integers(0, len(hold["credit_card"])))]
                        if card.balance_c + amt <= cents(card.credit_limit):
                            post(card, d, "card_purchase", cat, f"Card purchase - {cat}", amt, +1, "expense")
                            continue
                    if chk.balance_c - amt >= 0 or (sav.balance_c > amt):
                        ensure(amt)
                        if chk.balance_c >= amt:
                            post(chk, d, "debit_purchase", cat, f"Debit purchase - {cat}", amt, -1, "expense")

        # month-end non-cash postings (interest / returns)
        for a in accounts:
            if a.account_type in ("savings", "cd") and a.balance_c > 0:
                post(a, me, "interest_credit", "interest_credit", "Interest credited", max(1, int(a.balance_c * a.apy_pct / 1200)), +1, "non_cash")
            elif a.account_type == "ira":
                ret = float(hist.normal(0.006, 0.025))
                amt = max(1, abs(int(a.balance_c * ret)))
                post(a, me, "investment_return", "investment_return", "Investment return", amt, +1 if ret >= 0 else -1, "non_cash")
            elif a.account_type in LIABILITIES and a.balance_c > 0:
                post(a, me, "interest_accrual", "interest_accrual", "Interest accrued", max(1, int(a.month_open_c * a.apr_pct / 1200)), +1, "non_cash")

    txns = pd.DataFrame(ledger).sort_values(["posted_date", "order"], kind="stable").reset_index(drop=True)
    txns["transaction_id"] = [f"T{i + 1:06d}" for i in range(len(txns))]
    txns = txns.drop(columns="order")
    # re-derive balance_after per account in final order (same order as generated -> identical, asserted)
    chk_balance = txns.groupby("account_id")["balance_change"].cumsum()
    open_map = {a.account_id: a.opening_cents / 100 for a in accounts}
    recomputed = (chk_balance + txns["account_id"].map(open_map)).round(2)
    assert (recomputed - txns["balance_after"]).abs().max() < 0.005, "balance_after drifted from running balance"

    # ------------------------------------------------------------------ statements
    txns["month"] = pd.to_datetime(txns["posted_date"]).dt.to_period("M").dt.to_timestamp().dt.date
    stmts = []
    grouped = {k: g for k, g in txns.groupby(["account_id", "month"])}
    for a in accounts:
        running = a.opening_cents / 100
        for ms in months:
            g = grouped.get((a.account_id, ms))
            inc = float(g.loc[g.balance_change > 0, "amount"].sum()) if g is not None else 0.0
            dec = float(g.loc[g.balance_change < 0, "amount"].sum()) if g is not None else 0.0
            closing = round(running + inc - dec, 2)
            if g is not None:
                assert abs(closing - float(g["balance_after"].iloc[-1])) < 0.005
            stmts.append(dict(account_id=a.account_id, statement_month=ms, customer_id=a.customer_id,
                              opening_balance=round(running, 2), closing_balance=closing,
                              total_increases=round(inc, 2), total_decreases=round(dec, 2),
                              transaction_count=0 if g is None else len(g), source_type=SOURCE_TYPE))
            running = closing
    statements = pd.DataFrame(stmts)
    txns = txns.drop(columns="month")

    acct_rows = []
    for a in accounts:
        final = a.balance_c / 100
        assert final >= 0, f"negative final balance {a.account_id} {final}"
        acct_rows.append(dict(
            account_id=a.account_id, customer_id=a.customer_id, account_type=a.account_type, name=a.name,
            opened_date=a.opened_date, balance=round(final, 2), apy_pct=a.apy_pct, apr_pct=a.apr_pct,
            credit_limit=a.credit_limit, original_principal=a.original_principal, term_months=a.term_months,
            required_monthly_payment=a.payment, maturity_date=a.maturity_date, source_type=SOURCE_TYPE))

    pd.DataFrame(customers).to_csv(out_dir / "profiles.csv", index=False)
    pd.DataFrame(acct_rows).to_csv(out_dir / "accounts.csv", index=False)
    txn_cols = ["transaction_id", "posted_date", "customer_id", "account_id", "account_type", "transaction_type",
                "category", "description", "amount", "balance_change", "balance_after", "flow_class", "transfer_id", "source_type"]
    txns[txn_cols].to_csv(out_dir / "transactions.csv", index=False)
    statements.to_csv(out_dir / "monthly_statements.csv", index=False)

    manifest = {
        "label": "SYNTHETIC DEMO SUBSTITUTE - not the sponsor Lab_Package data",
        "source_type": SOURCE_TYPE,
        "snapshot_seed": SNAPSHOT_SEED, "history_seed": HISTORY_SEED,
        "window_start": START.isoformat(), "window_end": END.isoformat(), "as_of_date": END.isoformat(),
        "counts": {"customers": len(customers), "accounts": len(acct_rows), "transactions": int(len(txns)),
                   "statements": int(len(statements)),
                   "accounts_by_type": pd.DataFrame(acct_rows)["account_type"].value_counts().sort_index().to_dict()},
        "notes": ["The sponsor transaction count (21,225) cannot be reproduced without the sponsor generator.",
                  "No merchant field exists; descriptions are generic category labels.",
                  "External cash-management transfers are artificial and excluded from income/spending.",
                  "customer archetypes below are generator internals for evaluation only; never model features."],
        "generator_archetypes": {c["customer_id"]: str(archetypes[i]) for i, c in enumerate(customers)},
    }
    (out_dir / "history_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    from app.core.config import DEMO_PACKAGE_DIR
    print(json.dumps(generate(DEMO_PACKAGE_DIR)["counts"], indent=2))
