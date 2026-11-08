"""fin.futureyou: deterministic projections and what-if comparisons built on the finance engine.

Horizons: 30/60/90 days and 1/3/5 years (1, 2, 3, 12, 36, 60 months). Everything is a hypothetical projection from the
customer's own recent history, never a prediction or advice.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Connection, text

from app.pnc.finance import engine as E
from app.pnc.finance.evidence import Evidence, make_evidence

from .snapshot import Snapshot

D = Decimal
HORIZONS = {"30d": 1, "60d": 2, "90d": 3, "1y": 12, "3y": 36, "5y": 60}


class PurchaseSpec(BaseModel):
    price: Decimal = Field(default=Decimal("30000"), gt=0)
    down_payment: Decimal = Field(default=Decimal("5000"), ge=0)
    apr_pct: Decimal = Field(default=Decimal("8"), ge=0, le=60)
    term_months: int = Field(default=60, gt=0, le=120)

    @model_validator(mode="after")
    def _down_payment_not_above_price(self):
        if self.down_payment > self.price:
            raise ValueError("down_payment cannot exceed the purchase price")
        return self


class ScenarioSpec(BaseModel):
    label: str
    purchase: PurchaseSpec | None = None
    monthly_spending_change: Decimal = Decimal("0")        # negative = spend less
    monthly_income_change_pct: Decimal = Decimal("0")      # e.g. -10 = 10% less income
    one_time_expense: Decimal = Decimal("0")
    extra_monthly_savings: Decimal = Decimal("0")          # moves money to savings (same liquidity, earns APY)


def canonical_scenarios() -> list[ScenarioSpec]:
    """Baseline vs Alt A (canonical $30,000 car, $5,000 down, 8% APR, 60 months) vs Alt B (more down, shorter)."""
    return [ScenarioSpec(label="Baseline (no purchase)"),
            ScenarioSpec(label="Alt A: $30,000 / $5,000 down / 8% APR / 60 months", purchase=PurchaseSpec()),
            ScenarioSpec(label="Alt B: $30,000 / $10,000 down / 8% APR / 48 months",
                         purchase=PurchaseSpec(down_payment=Decimal("10000"), term_months=48))]


def _inputs(snap: Snapshot) -> dict[str, Any]:
    inc, cons, debt = snap.avg("income", 6), snap.avg("consumption_spending", 6), snap.avg("debt_payments", 6)
    ess = snap.avg("essential_spending", 6)
    miss = [n for n, v in (("income", inc), ("consumption_spending", cons), ("debt_payments", debt)) if v is None]
    sav = snap.accounts[snap.accounts.account_type == "savings"]
    sav_bal = sum((D(str(b)) for b in sav.balance), D(0))
    weighted = sum((D(str(b)) * D(str(a or 0)) / D(100) for b, a in zip(sav.balance, sav.apy_pct)), D(0))
    liquid = snap.liquid
    yield_rate = (weighted / liquid) if liquid > 0 else D(0)
    gross = D(str(snap.profile["annual_income"])) / D(12) if snap.profile.get("annual_income") else None
    req_debt = (sum((D(str(x)) for x in snap.obligations[snap.obligations["kind"] == "debt_payment"]["monthly_amount"]), D(0))
                if len(snap.obligations) else D(0))
    return {"income": inc, "consumption": cons, "debt": debt, "essential": ess, "liquid": liquid, "yield": yield_rate,
            "savings_balance": sav_bal, "gross_monthly": gross, "required_debt": req_debt, "missing": miss}


def project(snap: Snapshot, spec: ScenarioSpec) -> Evidence:
    b = _inputs(snap)
    if b["missing"]:
        return make_evidence("futureyou_projection", snap.as_of, {"label": spec.label}, {"projection": None},
                             missing=[f"{m} history" for m in b["missing"]], source_type="pnc_demo_data")
    income = b["income"] * (D(1) + spec.monthly_income_change_pct / D(100))
    spending = b["consumption"] + spec.monthly_spending_change
    pay, financed, down = D(0), D(0), D(0)
    steps = ["surplus = income - consumption - loan payments - new payment",
             "liquid_{t+1} = liquid_t*(1 + yield/12) + surplus; yield = weighted savings APY / liquid"]
    if spec.purchase:
        pc = E.calc_purchase_scenario(snap.as_of, spec.purchase.price, spec.purchase.down_payment,
                                      E.pct_to_rate(spec.purchase.apr_pct), spec.purchase.term_months)
        pay, financed, down = D(pc.results["monthly_payment"]), D(pc.results["financed_amount"]), spec.purchase.down_payment
        steps.append("new payment from calc_purchase_scenario (amortisation)")
    surplus = income - spending - b["debt"] - pay
    start = b["liquid"] - down - spec.one_time_expense
    series, bal, first_negative = {}, start, None
    for m in range(1, 61):
        bal = bal * (D(1) + b["yield"] / D(12)) + surplus
        if first_negative is None and bal < 0:
            first_negative = m
        if m in HORIZONS.values():
            series[next(k for k, v in HORIZONS.items() if v == m)] = E.money(bal)
    req_after = b["required_debt"] + pay
    dti = E.calc_dti(snap.as_of, req_after, b["gross_monthly"]).results["dti"]
    emerg = E.calc_emergency_months(snap.as_of, start, b["essential"]).results["months"] if b["essential"] else None
    flags = []
    if surplus < 0: flags.append("negative_monthly_surplus")
    if dti is not None and D(dti) > D("0.36"): flags.append("dti_above_36_percent")
    if emerg is not None and D(emerg) < 3: flags.append("emergency_fund_under_3_months")
    if first_negative: flags.append(f"liquid_balance_negative_in_month_{first_negative}")
    return make_evidence(
        "futureyou_projection", snap.as_of,
        {"label": spec.label, "spec": json.loads(spec.model_dump_json()), "avg_income_6m": income, "avg_consumption_6m": spending,
         "avg_loan_payments_6m": b["debt"], "starting_liquid": b["liquid"]},
        {"monthly_surplus": E.money(surplus), "new_monthly_payment": E.money(pay), "financed_amount": E.money(financed),
         "starting_liquidity_after_purchase": E.money(start), "projected_liquid_balance": series,
         "dti_after": dti, "emergency_months_after": emerg, "flags": flags,
         "summary": ("Under these assumptions the plan is sustainable." if not flags else
                     "Some strain indicators appear: " + ", ".join(flags))},
        formula_steps=steps,
        intermediates={"yield_rate": b["yield"], "required_debt_payments": b["required_debt"]},
        assumptions=["Income, spending and loan payments stay at their 6-month averages.",
                     "Savings earn the weighted APY of the customer's savings accounts; no taxes, fees, or inflation.",
                     "Purchase figures exclude taxes, registration, insurance and fuel."],
        limitations=["A projection from past data, not a forecast; real months vary.", "Synthetic demo data."],
        source_type="pnc_demo_data", units={"projected_liquid_balance": "USD"})


def compare(snap: Snapshot, specs: list[ScenarioSpec] | None = None) -> dict:
    specs = specs or canonical_scenarios()
    evs = [project(snap, s) for s in specs]
    base = evs[0].results.get("projected_liquid_balance")
    rows = []
    for s, e in zip(specs, evs):
        r = e.results
        delta = ({k: E.money(D(v) - D(base[k])) for k, v in r["projected_liquid_balance"].items()}
                 if base and r.get("projected_liquid_balance") else None)
        rows.append({"label": s.label, "evidence": e.model_dump(mode="json"), "vs_baseline_liquid_delta": delta})
    return {"as_of": snap.as_of.isoformat(), "scenarios": rows}


def persist(conn: Connection, customer_id: str, kind: str, spec: ScenarioSpec, evidence: Evidence) -> dict:
    sid = conn.execute(text(
        "INSERT INTO pnc_financial_scenarios(customer_id, kind, label, inputs) VALUES (:c,:k,:l,CAST(:i AS jsonb)) RETURNING scenario_id"),
        {"c": customer_id, "k": kind, "l": spec.label, "i": spec.model_dump_json()}).scalar_one()
    rid = conn.execute(text(
        "INSERT INTO pnc_scenario_results(scenario_id, customer_id, evidence) VALUES (:s,:c,CAST(:e AS jsonb)) RETURNING result_id"),
        {"s": sid, "c": customer_id, "e": evidence.model_dump_json()}).scalar_one()
    return {"scenario_id": str(sid), "result_id": str(rid)}
