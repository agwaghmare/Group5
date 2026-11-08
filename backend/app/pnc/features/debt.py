"""fin.debt: amortisation, snowball vs avalanche, hypothetical refinance and consolidation.

All outputs are hypothetical illustrations from the customer's own balances; not offers, quotes or advice.
"""
from __future__ import annotations

import math
from decimal import Decimal

from app.pnc.errors import NotFound
from app.pnc.finance import engine as E
from app.pnc.finance.evidence import make_evidence

from .snapshot import Snapshot

D = Decimal
CARD_MIN_RATE, CARD_MIN_FLOOR = D("0.02"), D("25")


def debts_from_snapshot(snap: Snapshot) -> list[E.Debt]:
    out = []
    for a in snap.accounts.itertuples():
        if a.account_type not in ("credit_card", "auto_loan", "personal_loan", "mortgage"):
            continue
        bal = D(str(a.balance))
        if bal <= 0:
            continue
        if a.account_type == "credit_card":
            minimum = max(CARD_MIN_FLOOR, E.money(bal * CARD_MIN_RATE))
        else:
            minimum = D(str(a.required_monthly_payment)) if a.required_monthly_payment == a.required_monthly_payment else D(0)
        out.append(E.Debt(f"{a.name} ({a.account_id})", bal, E.pct_to_rate(a.apr_pct or 0), minimum))
    return out


def remaining_months(balance: Decimal, annual_rate: Decimal, pay: Decimal) -> int | None:
    r = annual_rate / D(12)
    if pay <= 0:
        return None
    if r == 0:
        return int(math.ceil(float(balance / pay)))
    x = float(balance * r / pay)
    return None if x >= 1 else int(math.ceil(-math.log(1 - x) / math.log(1 + float(r))))


def amortization(snap: Snapshot, account_id: str, extra_monthly: Decimal = D("0")) -> dict:
    row = snap.accounts[snap.accounts.account_id == account_id]
    if row.empty:
        raise NotFound("account not found")
    a = row.iloc[0]
    debt = next((d for d in debts_from_snapshot(snap) if d.name.endswith(f"({account_id})")), None)
    if debt is None:
        raise ValueError("account is not an outstanding liability")
    n = remaining_months(debt.balance, debt.apr, debt.min_payment)
    if n is None:
        return make_evidence("debt_amortization", snap.as_of, {"account_id": account_id}, {"schedule": None},
                             missing=["payment large enough to cover monthly interest"], source_type="pnc_demo_data").model_dump(mode="json")
    ev = E.calc_amortization(snap.as_of, debt.balance, debt.apr, n, extra_monthly, source="pnc_demo_data")
    d = ev.model_dump(mode="json")
    d["results"]["account"] = {"account_id": account_id, "type": a.account_type, "balance": str(debt.balance), "apr_pct": a.apr_pct}
    d["limitations"] = d["limitations"] + ["Remaining term is inferred from the current balance, APR and required/minimum payment."]
    return d


def payoff_compare(snap: Snapshot, extra_monthly: Decimal) -> dict:
    debts = debts_from_snapshot(snap)
    if not debts:
        return {"results": {"debts": []}, "note": "No outstanding debts."}
    return E.calc_debt_payoff_compare(snap.as_of, debts, extra_monthly, source="pnc_demo_data").model_dump(mode="json")


def refinance_scenario(snap: Snapshot, account_id: str, new_apr_pct: Decimal, new_term_months: int, fee: Decimal = D("0")) -> dict:
    if snap.accounts[snap.accounts.account_id == account_id].empty:
        raise NotFound("account not found")
    debt = next((d for d in debts_from_snapshot(snap) if d.name.endswith(f"({account_id})")), None)
    if debt is None:
        raise ValueError("account is not an outstanding liability")
    n_old = remaining_months(debt.balance, debt.apr, debt.min_payment)
    if n_old is None:
        raise ValueError("current payment does not cover interest; refinance comparison unavailable")
    old = E.amortize(debt.balance, debt.apr, n_old)
    new_principal = debt.balance + fee
    new = E.amortize(new_principal, E.pct_to_rate(new_apr_pct), new_term_months)
    old_int, new_int = sum((r.interest for r in old), D(0)), sum((r.interest for r in new), D(0))
    new_pay = E.payment(new_principal, E.pct_to_rate(new_apr_pct), new_term_months)
    # break-even: first month where cumulative cost (new incl. fee already financed) is below old
    cum_old = cum_new = D(0)
    breakeven = None
    for m in range(1, max(len(old), len(new)) + 1):
        cum_old += old[m - 1].payment if m <= len(old) else D(0)
        cum_new += new[m - 1].payment if m <= len(new) else D(0)
        if breakeven is None and cum_new < cum_old:
            breakeven = m
    ev = make_evidence("hypothetical_refinance", snap.as_of,
                       {"account_id": account_id, "balance": debt.balance, "current_apr": debt.apr, "new_apr_pct": new_apr_pct,
                        "new_term_months": new_term_months, "fee": fee},
                       {"current_payment": E.money(debt.min_payment), "new_payment": E.money(new_pay),
                        "payment_change": E.money(new_pay - debt.min_payment),
                        "current_remaining_interest": E.money(old_int), "new_total_interest": E.money(new_int),
                        "interest_difference": E.money(old_int - new_int),
                        "total_cost_difference": E.money(sum((r.payment for r in old), D(0)) - sum((r.payment for r in new), D(0))),
                        "current_remaining_months": len(old), "new_months": len(new), "breakeven_month": breakeven,
                        "verdict": "lower_total_cost" if sum((r.payment for r in new), D(0)) < sum((r.payment for r in old), D(0)) else "higher_total_cost"},
                       formula_steps=["current = amortisation of balance at current APR and payment", "new = amortisation of (balance + fee) at new APR/term"],
                       assumptions=["Fee is financed into the new loan.", "No prepayment penalties."],
                       limitations=["HYPOTHETICAL ONLY: not an offer, quote, or approval; actual rates depend on underwriting."],
                       source_type="pnc_demo_data")
    return ev.model_dump(mode="json")


def consolidation_scenario(snap: Snapshot, account_ids: list[str], new_apr_pct: Decimal, new_term_months: int, fee: Decimal = D("0")) -> dict:
    unknown = sorted(set(account_ids) - set(snap.accounts.account_id))
    if unknown:
        raise NotFound(f"account not found: {', '.join(unknown)}")
    chosen = [d for d in debts_from_snapshot(snap) if any(d.name.endswith(f"({i})") for i in account_ids)]
    if not chosen:
        raise ValueError("no outstanding liabilities selected")
    total = sum((d.balance for d in chosen), D(0))
    cur_pay = sum((d.min_payment for d in chosen), D(0))
    cur_int = D(0)
    for d in chosen:
        n = remaining_months(d.balance, d.apr, d.min_payment)
        if n is None:
            raise ValueError(f"{d.name}: payment does not cover interest")
        cur_int += sum((r.interest for r in E.amortize(d.balance, d.apr, n)), D(0))
    new_pay = E.payment(total + fee, E.pct_to_rate(new_apr_pct), new_term_months)
    new_int = sum((r.interest for r in E.amortize(total + fee, E.pct_to_rate(new_apr_pct), new_term_months)), D(0))
    weighted = sum((d.balance * d.apr for d in chosen), D(0)) / total
    ev = make_evidence("hypothetical_consolidation", snap.as_of,
                       {"account_ids": account_ids, "new_apr_pct": new_apr_pct, "new_term_months": new_term_months, "fee": fee},
                       {"combined_balance": E.money(total), "current_combined_payment": E.money(cur_pay),
                        "new_payment": E.money(new_pay), "weighted_current_apr_pct": E.money(E.rate_to_pct(weighted)),
                        "current_remaining_interest": E.money(cur_int), "new_total_interest": E.money(new_int),
                        "interest_difference": E.money(cur_int - new_int),
                        "caution": "A longer term can lower the payment while raising total interest." if new_int > cur_int else None},
                       formula_steps=["current interest = sum of each debt's remaining-interest amortisation",
                                      "new = one loan of (combined balance + fee) at new APR/term"],
                       limitations=["HYPOTHETICAL ONLY: not an offer or approval."], source_type="pnc_demo_data")
    return ev.model_dump(mode="json")
