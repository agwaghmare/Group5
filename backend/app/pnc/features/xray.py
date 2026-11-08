"""fin.xray: explainable financial-health indicators (ten indicators, each with raw value, normalised score,
status, thresholds, source, inputs, explanation and a safe action). The overall score is a transparent weighted
average of the indicators that could be computed; it is NOT a credit score."""
from __future__ import annotations

import statistics
from decimal import Decimal

import numpy as np

from app.pnc.finance import engine as E
from app.pnc.finance.evidence import ENGINE_VERSION, make_evidence

from .snapshot import Snapshot, net_worth_series

D = Decimal
# id: (label, direction, (risk_anchor, watch, ok, strong), weight, unit)
SPEC = {
    "savings_rate": ("Savings rate", "higher", (0.0, 0.05, 0.10, 0.15), 1.5, "fraction of income"),
    "emergency_fund_months": ("Emergency fund", "higher", (0.0, 1.0, 3.0, 6.0), 2.0, "months of essential spending"),
    "debt_to_income": ("Debt-to-income", "lower", (0.50, 0.43, 0.36, 0.20), 2.0, "fraction of gross income"),
    "credit_utilization": ("Credit-card utilization", "lower", (0.80, 0.50, 0.30, 0.10), 1.5, "fraction of limits"),
    "cash_flow_surplus_ratio": ("Cash-flow surplus", "higher", (-0.10, 0.0, 0.08, 0.20), 2.0, "fraction of income"),
    "spending_stability": ("Spending stability", "lower", (0.50, 0.35, 0.20, 0.10), 0.75, "coefficient of variation"),
    "income_stability": ("Income stability", "lower", (0.50, 0.35, 0.20, 0.10), 1.0, "coefficient of variation"),
    "obligation_coverage_months": ("Obligation coverage", "higher", (0.0, 1.0, 3.0, 6.0), 1.0, "months of fixed obligations"),
    "net_worth_trend_6m": ("Net-worth trend (6 months)", "higher", (-0.10, -0.02, 0.0, 0.05), 1.0, "fractional change"),
    "debt_trend_6m": ("Debt trend (6 months)", "lower", (0.10, 0.02, 0.0, -0.05), 0.75, "fractional change"),
}
ACTIONS = {
    "strong": "Keep doing what you are doing; review this indicator quarterly.",
    "ok": "You are on track. A small, steady improvement here would strengthen your position.",
    "watch": "Consider a modest change this month; see the linked explanation for options.",
    "risk": "This is worth attention soon. Small safe steps, such as trimming one recurring cost or a scheduled transfer, help.",
}


def normalize(value: float, direction: str, anchors: tuple) -> float:
    xs = list(anchors)
    ys = [0.0, 40.0, 70.0, 100.0]
    if direction == "lower":
        xs, ys = xs[::-1], ys[::-1]
    return float(np.interp(value, xs, ys))


def status_for(value: float, direction: str, anchors: tuple) -> str:
    _, watch, ok, strong = anchors
    if direction == "higher":
        return "strong" if value >= strong else "ok" if value >= ok else "watch" if value >= watch else "risk"
    return "strong" if value <= strong else "ok" if value <= ok else "watch" if value <= watch else "risk"


def _cv(vals: list[Decimal]) -> float | None:
    if len(vals) < 3:
        return None
    m = statistics.fmean(float(v) for v in vals)
    return None if m <= 0 else statistics.pstdev(float(v) for v in vals) / m


def _pack(iid: str, raw: float | None, inputs: dict, source: str, explanation: str, missing: list[str] | None = None,
          evidence: dict | None = None) -> dict:
    label, direction, anchors, weight, unit = SPEC[iid]
    base = {"id": iid, "label": label, "unit": unit, "direction": f"{direction}_is_better",
            "thresholds": {"risk_anchor": anchors[0], "watch": anchors[1], "ok": anchors[2], "strong": anchors[3]},
            "weight": weight, "source": source, "inputs": inputs, "evidence": evidence}
    if raw is None:
        return {**base, "raw": None, "normalized": None, "status": "unavailable", "explanation": explanation,
                "missing_inputs": missing or [], "safe_action": "Not enough data to assess this indicator yet."}
    st = status_for(raw, direction, anchors)
    return {**base, "raw": round(raw, 4), "normalized": round(normalize(raw, direction, anchors), 1), "status": st,
            "explanation": explanation, "missing_inputs": [], "safe_action": ACTIONS[st]}


def compute_indicators(snap: Snapshot) -> list[dict]:
    out: list[dict] = []
    gross_m = D(str(snap.profile["annual_income"])) / D(12) if snap.profile.get("annual_income") else None
    n3 = min(3, len(snap.monthly))
    inc3, ess3 = snap.avg("income", 3), snap.avg("essential_spending", 3)
    cons3, debt3 = snap.avg("consumption_spending", 3), snap.avg("debt_payments", 3)
    sav3 = snap.avg("savings_transfers_out", 3)
    src3 = f"gold_monthly_cashflow, last {n3} complete month(s) ending {snap.monthly['month'].max() if len(snap.monthly) else 'n/a'}"

    # 1 savings rate
    if inc3 and inc3 > 0 and sav3 is not None:
        r = float(sav3 / inc3)
        out.append(_pack("savings_rate", r, {"avg_savings_transfers": str(sav3), "avg_income": str(inc3)}, src3,
                         f"You moved about {r:.1%} of income into savings and retirement transfers over the last {n3} months."))
    else:
        out.append(_pack("savings_rate", None, {}, src3, "Savings rate needs recent income and transfers.", ["monthly income"]))

    # 2 emergency fund
    ef = E.calc_emergency_months(snap.as_of, snap.sum_balance({"checking", "savings"}), ess3)
    out.append(_pack("emergency_fund_months", None if ef.results["months"] is None else float(ef.results["months"]),
                     {"liquid_balance": str(snap.liquid), "avg_essential_monthly": None if ess3 is None else str(ess3)},
                     "account balances at as_of + " + src3,
                     f"Checking and savings cover about {ef.results['months']} months of essential spending." if ef.results["months"] else
                     "Essential spending is unavailable.", ef.missing_inputs, ef.model_dump(mode="json")))

    # 3 debt to income (gross income from the profile)
    # required debt payments: loan contract payments + card minimums (obligations); card settlements are not added again
    if len(snap.obligations):
        req_debt = sum((D(str(x)) for x in snap.obligations[snap.obligations["kind"] == "debt_payment"]["monthly_amount"]), D(0))
    else:
        req_debt = D(0) if snap.liabilities == 0 else None
    dti = E.calc_dti(snap.as_of, req_debt, gross_m)
    out.append(_pack("debt_to_income", None if dti.results["dti"] is None else float(dti.results["dti"]),
                     {"required_monthly_debt_payments": None if req_debt is None else str(req_debt), "gross_monthly_income": None if gross_m is None else str(gross_m)},
                     "profile annual income + pnc_recurring_obligations (loan terms + card minimums)",
                     f"Debt payments are about {float(dti.results['dti']):.1%} of gross monthly income." if dti.results["dti"] is not None else "DTI inputs missing.",
                     dti.missing_inputs, dti.model_dump(mode="json")))

    # 4 utilization
    cards = snap.accounts[snap.accounts.account_type == "credit_card"]
    if len(cards) and cards.credit_limit.notna().all():
        ut = E.calc_utilization(snap.as_of, sum((D(str(b)) for b in cards.balance), D(0)), sum((D(str(l)) for l in cards.credit_limit), D(0)))
        out.append(_pack("credit_utilization", float(ut.results["utilization"]), ut.inputs, "account balances and limits at as_of",
                         f"Card balances use {float(ut.results['utilization']):.1%} of your combined limits.", [], ut.model_dump(mode="json")))
    else:
        out.append(_pack("credit_utilization", None, {}, "accounts", "No credit card with a known limit.", ["credit card limit"]))

    # 5 cash-flow surplus ratio
    if inc3 and inc3 > 0 and cons3 is not None and debt3 is not None:
        cs = E.calc_cash_surplus(snap.as_of, inc3, cons3, debt3)
        r = float(D(cs.results["cash_surplus"]) / inc3)
        out.append(_pack("cash_flow_surplus_ratio", r, cs.inputs, src3,
                         f"After spending and debt payments you keep about {r:.1%} of income each month.", [], cs.model_dump(mode="json")))
    else:
        out.append(_pack("cash_flow_surplus_ratio", None, {}, src3, "Cash-flow surplus needs income and spending history.", ["monthly cash flow"]))

    # 6/7 stability (6 months)
    cv_sp, cv_in = _cv(snap.recent("consumption_spending", 6)), _cv(snap.recent("income", 6))
    out.append(_pack("spending_stability", cv_sp, {"months": min(6, len(snap.monthly))}, "gold_monthly_cashflow, last 6 months",
                     "How much monthly spending varies (lower is steadier)." if cv_sp is not None else "Needs at least 3 months of spending.",
                     [] if cv_sp is not None else ["3+ months of spending"]))
    out.append(_pack("income_stability", cv_in, {"months": min(6, len(snap.monthly))}, "gold_monthly_cashflow, last 6 months",
                     "How much monthly income varies (lower is steadier)." if cv_in is not None else "Needs at least 3 months of income.",
                     [] if cv_in is not None else ["3+ months of income"]))

    # 8 obligation coverage
    fixed = snap.obligations[snap.obligations["kind"].isin(["housing", "debt_payment", "utility", "insurance"])] if len(snap.obligations) else snap.obligations
    fixed_total = sum((D(str(x)) for x in fixed["monthly_amount"]), D(0)) if len(fixed) else None
    if fixed_total and fixed_total > 0:
        cov = float(snap.liquid / fixed_total)
        out.append(_pack("obligation_coverage_months", cov, {"liquid": str(snap.liquid), "fixed_obligations_monthly": str(fixed_total)},
                         "pnc_recurring_obligations + balances", f"Liquid balances cover about {cov:.1f} months of fixed obligations."))
    else:
        out.append(_pack("obligation_coverage_months", None, {}, "pnc_recurring_obligations", "No fixed obligations on file.", ["recurring obligations"]))

    # 9/10 trends over 6 months of month-end history
    nw = net_worth_series(snap)
    if len(nw) >= 7 and abs(nw.iloc[-7]) > 0:
        ch = float((nw.iloc[-1] - nw.iloc[-7]) / abs(nw.iloc[-7]))
        out.append(_pack("net_worth_trend_6m", ch, {"start": round(float(nw.iloc[-7]), 2), "end": round(float(nw.iloc[-1]), 2)},
                         "pnc_balance_history", f"Net worth changed {ch:+.1%} over six months."))
    else:
        out.append(_pack("net_worth_trend_6m", None, {}, "pnc_balance_history", "Needs seven month-ends of history.", ["7 months of balances"]))
    bh = snap.balance_history
    liab = bh[bh.account_type.isin(["credit_card", "auto_loan", "personal_loan", "mortgage"])].groupby("as_of")["balance"].sum().astype(float) if len(bh) else None
    if liab is not None and len(liab) >= 7 and liab.iloc[-7] > 0:
        ch = float((liab.iloc[-1] - liab.iloc[-7]) / liab.iloc[-7])
        out.append(_pack("debt_trend_6m", ch, {"start": round(float(liab.iloc[-7]), 2), "end": round(float(liab.iloc[-1]), 2)},
                         "pnc_balance_history", f"Total debt changed {ch:+.1%} over six months."))
    else:
        out.append(_pack("debt_trend_6m", None, {}, "pnc_balance_history", "Needs seven month-ends of liability history.", ["7 months of balances"]))
    return out


def overall(indicators: list[dict]) -> dict:
    ok = [i for i in indicators if i["normalized"] is not None]
    if not ok:
        return {"score": None, "band": "unavailable", "indicators_used": 0, "indicators_total": len(indicators)}
    w = sum(i["weight"] for i in ok)
    score = sum(i["normalized"] * i["weight"] for i in ok) / w
    band = "Strong" if score >= 75 else "Stable" if score >= 55 else "Watch" if score >= 35 else "Needs attention"
    return {"score": round(score, 1), "band": band, "indicators_used": len(ok), "indicators_total": len(indicators),
            "unavailable": [i["id"] for i in indicators if i["normalized"] is None],
            "method": "weighted average of normalised indicator scores (anchors map risk->0, watch->40, ok->70, strong->100)",
            "disclaimer": "Educational summary of your own data. Not a credit score and not financial advice."}


def build_xray(snap: Snapshot) -> dict:
    inds = compute_indicators(snap)
    ev = make_evidence("financial_xray", snap.as_of, {"customer_id": snap.customer_id}, {"overall": overall(inds)},
                       formula_steps=["indicators computed from point-in-time data <= as_of", "overall = weighted mean of normalised scores"],
                       missing=snap.missing, source_type="pnc_demo_data",
                       limitations=["Based on 30 synthetic customers' demo data.", "Indicators describe history; they do not predict outcomes."])
    return {"as_of": snap.as_of.isoformat(), "customer_id": snap.customer_id, "overall": overall(inds), "indicators": inds,
            "evidence": ev.model_dump(mode="json"), "engine_version": ENGINE_VERSION}
