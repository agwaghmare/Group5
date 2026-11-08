"""Customer API: /api/v1/pnc. Every route requires the customer role; data access is limited by database RLS to the
authenticated customer's own rows."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text

from app.pnc.errors import NotFound
from app.pnc.features import debt as debt_f
from app.pnc.features import fraud as fraud_f
from app.pnc.features import futureyou as fy
from app.pnc.features import goals as goals_f
from app.pnc.features import immune as immune_f
from app.pnc.features import spending as spend_f
from app.pnc.features.snapshot import load_snapshot
from app.pnc.features.xray import build_xray
from app.pnc.ml import cashflow as ml_cashflow

from .deps import Principal, as_of_param, require_roles, run

router = APIRouter(prefix="/api/v1/pnc", tags=["customer"])
Cust = Depends(require_roles("customer"))
D = Decimal


def _snap(conn, p: Principal, as_of: date):
    return load_snapshot(conn, p.actor_id, as_of)


def _ser(rows) -> list[dict]:
    out = []
    for r in rows:
        d = {}
        for k, v in dict(r).items():
            d[k] = str(v) if isinstance(v, Decimal) else (v.isoformat() if hasattr(v, "isoformat") else v)
        out.append(d)
    return out


@router.get("/profile")
def profile(request: Request, p: Principal = Cust):
    def fn(c):
        r = c.execute(text("SELECT customer_id, display_name, age, city, pay_frequency, annual_income, income_sources_count, credit_score, "
                           "preferred_channel, marketing_consent, dataset_version, source_type FROM pnc_customers")).mappings().one()
        return _ser([r])[0]
    return run(p, fn, request=request)


@router.get("/accounts")
def accounts(request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param)):
    def fn(c):
        s = _snap(c, p, as_of)
        return {"as_of": as_of.isoformat(), "accounts": _ser(s.accounts.to_dict("records")),
                "totals": {"assets": str(s.assets), "liabilities": str(s.liabilities), "net_worth": str(s.assets - s.liabilities)},
                "note": "Liability balances are positive numbers."}
    return run(p, fn, request=request)


@router.get("/transactions")
def transactions(request: Request, p: Principal = Cust, account_id: str | None = None, category: str | None = None,
                 flow_class: str | None = None, date_from: date | None = None, date_to: date | None = None,
                 limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    def fn(c):
        where, prm = [], {"n": limit, "o": offset}
        for col, val in (("account_id", account_id), ("category", category), ("flow_class", flow_class)):
            if val:
                where.append(f"{col} = :{col}"); prm[col] = val
        if date_from: where.append("posted_date >= :df"); prm["df"] = date_from
        if date_to: where.append("posted_date <= :dt"); prm["dt"] = date_to
        sql = ("SELECT transaction_id, posted_date, account_id, account_type, transaction_type, category, description, amount, "
               "balance_change, balance_after, flow_class, transfer_id FROM pnc_transactions"
               + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY posted_date DESC, transaction_id DESC LIMIT :n OFFSET :o")
        rows = c.execute(text(sql), prm).mappings().all()
        return {"transactions": _ser(rows), "limit": limit, "offset": offset, "note": "No merchant field exists in the data."}
    return run(p, fn, request=request)


@router.get("/accounts/{account_id}/history")
def account_history(account_id: str, request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param)):
    def fn(c):
        rows = c.execute(text("SELECT as_of, balance FROM pnc_balance_history WHERE account_id = :a AND as_of <= :d ORDER BY as_of"),
                         {"a": account_id, "d": as_of}).mappings().all()
        if not rows:
            raise NotFound("account not found")
        return {"account_id": account_id, "granularity": "month-end", "history": _ser(rows)}
    return run(p, fn, request=request)


@router.get("/financial-xray")
def xray(request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param)):
    return run(p, lambda c: build_xray(_snap(c, p, as_of)), request=request)


@router.get("/health-indicators")
def health_indicators(request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param)):
    def fn(c):
        x = build_xray(_snap(c, p, as_of))
        return {"as_of": x["as_of"], "overall": x["overall"], "indicators": x["indicators"]}
    return run(p, fn, request=request)


@router.get("/cash-flow")
def cash_flow(request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param), months: int = Query(12, ge=1, le=24)):
    def fn(c):
        s = _snap(c, p, as_of)
        m = s.monthly.tail(months)
        return {"as_of": as_of.isoformat(), "months": _ser(m.to_dict("records")),
                "definitions": {"consumption_spending": "expenses excluding debt payments; card purchases counted once at purchase",
                                "debt_payments": "loan payments from checking (counted once)",
                                "card_settlements": "card payments from checking; settle spending already counted, not added to outflow",
                                "excluded": "internal transfers, external cash-management flows (artificial), non-cash postings"}}
    return run(p, fn, request=request)


@router.get("/upcoming-obligations")
def upcoming(request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param), days: int = Query(30, ge=1, le=90)):
    def fn(c):
        return spend_f.safe_spend(_snap(c, p, as_of), days)["results"].get("upcoming_obligations", [])
    return {"as_of": as_of.isoformat(), "days": days, "obligations": run(p, fn, request=request)}


@router.get("/forecasts/balances")
def forecast_balances(request: Request, p: Principal = Cust, months: int = Query(3, ge=1, le=12)):
    def fn(c):
        s = _snap(c, p, as_of_param(None))      # the customer's own RLS-scoped history only; model chosen offline
        surplus = [float(a) - float(b) - float(d) for a, b, d in zip(s.monthly["income"], s.monthly["consumption_spending"], s.monthly["debt_payments"])]
        fc = ml_cashflow.forecast_from_series(surplus, months)
        bal, series = s.liquid, []
        for f in fc["forecast"]:
            bal = bal + D(str(f["point"]))
            series.append({"month_ahead": f["month_ahead"], "liquid_balance_point": str(bal.quantize(D("0.01")))})
        return {**fc, "starting_liquid_balance": str(s.liquid), "projected_liquid_balance": series,
                "assumption": "liquid balance moves by the forecast net surplus; interest on savings ignored"}
    return run(p, fn, request=request)


@router.get("/forecasts/stress")
def forecast_stress(request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param), markov: bool = False):
    def fn(c):
        s = _snap(c, p, as_of)
        out = immune_f.run_shocks(s)
        if markov:
            out["markov"] = immune_f.markov_view(s)
        return out
    return run(p, fn, request=request)


class PurchaseIn(BaseModel):
    price: Decimal = Field(default=D("30000"), gt=0)
    down_payment: Decimal = Field(default=D("5000"), ge=0)
    apr_pct: Decimal = Field(default=D("8"), ge=0, le=60)
    term_months: int = Field(default=60, gt=0, le=120)
    label: str | None = None
    save: bool = True

    @model_validator(mode="after")
    def _down_payment_not_above_price(self):
        if self.down_payment > self.price:
            raise ValueError("down_payment cannot exceed the purchase price")
        return self


@router.post("/scenarios/purchase")
def scenario_purchase(body: PurchaseIn, request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param)):
    def fn(c):
        s = _snap(c, p, as_of)
        spec = fy.ScenarioSpec(label=body.label or f"Purchase {body.price} / {body.down_payment} down / {body.apr_pct}% / {body.term_months}m",
                               purchase=fy.PurchaseSpec(price=body.price, down_payment=body.down_payment, apr_pct=body.apr_pct, term_months=body.term_months))
        base, alt = fy.project(s, fy.ScenarioSpec(label="Baseline (no purchase)")), fy.project(s, spec)
        saved = fy.persist(c, p.actor_id, "purchase", spec, alt) if body.save else None
        return {"baseline": base.model_dump(mode="json"), "scenario": alt.model_dump(mode="json"), "saved": saved}
    return run(p, fn, request=request)


class CompareIn(BaseModel):
    scenarios: list[fy.ScenarioSpec] | None = None
    save: bool = True


@router.post("/scenarios/compare")
def scenario_compare(body: CompareIn, request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param)):
    def fn(c):
        s = _snap(c, p, as_of)
        specs = body.scenarios or fy.canonical_scenarios()
        out = fy.compare(s, specs)
        if body.save:
            for spec, row in zip(specs, out["scenarios"]):
                from app.pnc.finance.evidence import Evidence
                row["saved"] = fy.persist(c, p.actor_id, "compare", spec, Evidence.model_validate(row["evidence"]))
        return out
    return run(p, fn, request=request)


@router.get("/scenarios")
def scenarios(request: Request, p: Principal = Cust):
    def fn(c):
        return _ser(c.execute(text("SELECT scenario_id, kind, label, created_at FROM pnc_financial_scenarios ORDER BY created_at DESC LIMIT 100")).mappings())
    return {"scenarios": run(p, fn, request=request)}


@router.get("/scenarios/{scenario_id}")
def scenario_detail(scenario_id: str, request: Request, p: Principal = Cust):
    def fn(c):
        s = c.execute(text("SELECT scenario_id, kind, label, inputs, created_at FROM pnc_financial_scenarios WHERE scenario_id = CAST(:i AS uuid)"),
                      {"i": scenario_id}).mappings().first()
        if not s:
            raise NotFound("scenario not found")
        r = c.execute(text("SELECT result_id, evidence, created_at FROM pnc_scenario_results WHERE scenario_id = CAST(:i AS uuid) ORDER BY created_at"),
                      {"i": scenario_id}).mappings().all()
        return {**_ser([s])[0], "results": _ser(r)}
    return run(p, fn, request=request)


# ---------------------------------------------------------------- goals
@router.get("/goals")
def goals_list(request: Request, p: Principal = Cust):
    return {"goals": _ser(run(p, goals_f.list_goals, request=request))}


@router.post("/goals", status_code=201)
def goals_create(body: goals_f.GoalIn, request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param)):
    return _ser([run(p, lambda c: goals_f.create(c, p.actor_id, body, as_of), request=request)])[0]


@router.get("/goals/{goal_id}")
def goals_get(goal_id: str, request: Request, p: Principal = Cust):
    def fn(c):
        g = goals_f.get(c, goal_id)
        if not g:
            raise NotFound("goal not found")
        return _ser([g])[0]
    return run(p, fn, request=request)


class GoalPatch(BaseModel):
    name: str | None = None
    target_amount: Decimal | None = Field(default=None, gt=0)
    deadline: date | None = None
    planned_monthly_contribution: Decimal | None = Field(default=None, ge=0)
    current_amount: Decimal | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, pattern="^(active|completed|abandoned)$")


@router.patch("/goals/{goal_id}")
def goals_patch(goal_id: str, body: GoalPatch, request: Request, p: Principal = Cust):
    def fn(c):
        g = goals_f.update(c, goal_id, body.model_dump(exclude_none=True))
        if not g:
            raise NotFound("goal not found")
        return _ser([g])[0]
    return run(p, fn, request=request)


@router.delete("/goals/{goal_id}", status_code=204)
def goals_delete(goal_id: str, request: Request, p: Principal = Cust):
    if not run(p, lambda c: goals_f.delete(c, goal_id), request=request):
        raise HTTPException(404, "goal not found")


@router.post("/goals/{goal_id}/calculate-plan")
def goals_plan(goal_id: str, request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param), annual_rate_pct: Decimal = Query(D("0"), ge=0, le=20)):
    def fn(c):
        g = goals_f.get(c, goal_id)
        if not g:
            raise NotFound("goal not found")
        cons = (g.get("constraints") or {}).get("max_monthly_contribution")
        g["max_monthly_contribution"] = cons
        plan = goals_f.calculate_plan(_snap(c, p, as_of), g, as_of, annual_rate_pct / D(100))
        goals_f.save_plan(c, goal_id, plan)
        return plan
    return run(p, fn, request=request)


# ---------------------------------------------------------------- spending
@router.get("/safe-spend")
def safe_spend(request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param), horizon_days: int = Query(30, ge=1, le=60)):
    def fn(c):
        s = _snap(c, p, as_of)
        contrib = sum((D(str(g["planned_monthly_contribution"])) for g in goals_f.list_goals(c)
                       if g["status"] == "active" and g["planned_monthly_contribution"] is not None), D(0)) * D(horizon_days) / D("30.4")
        return spend_f.safe_spend(s, horizon_days, contrib)
    return run(p, fn, request=request)


@router.get("/missions")
def missions(request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param)):
    def fn(c):
        s = _snap(c, p, as_of)
        return {"as_of": as_of.isoformat(), "missions": spend_f.missions(build_xray(s), s)}
    return run(p, fn, request=request)


@router.get("/recurring-charges")
def recurring(request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param)):
    return run(p, lambda c: {**spend_f.recurring_charges(c, p.actor_id, as_of), "possible_duplicates": spend_f.possible_duplicates(c, p.actor_id, as_of)}, request=request)


@router.get("/subscription-burden")
def sub_burden(request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param)):
    return run(p, lambda c: spend_f.subscription_burden(c, _snap(c, p, as_of)), request=request)


@router.get("/spending-trends")
def trends(request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param)):
    return run(p, lambda c: spend_f.spending_trends(_snap(c, p, as_of), c), request=request)


@router.get("/rewards/compare")
def rewards(request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param)):
    return run(p, lambda c: spend_f.rewards_compare(c, _snap(c, p, as_of)), request=request)


# ---------------------------------------------------------------- debt
@router.get("/debt/amortization")
def debt_amort(account_id: str, request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param), extra_monthly: Decimal = Query(D("0"), ge=0)):
    return run(p, lambda c: debt_f.amortization(_snap(c, p, as_of), account_id, extra_monthly), request=request)


@router.get("/debt/payoff-compare")
def debt_compare(request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param), extra_monthly: Decimal = Query(D("100"), ge=0)):
    return run(p, lambda c: debt_f.payoff_compare(_snap(c, p, as_of), extra_monthly), request=request)


class RefiIn(BaseModel):
    account_id: str
    new_apr_pct: Decimal = Field(ge=0, le=60)
    new_term_months: int = Field(gt=0, le=480)
    fee: Decimal = Field(default=D("0"), ge=0)


@router.post("/debt/refinance-scenario")
def debt_refi(body: RefiIn, request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param)):
    return run(p, lambda c: debt_f.refinance_scenario(_snap(c, p, as_of), body.account_id, body.new_apr_pct, body.new_term_months, body.fee), request=request)


class ConsolIn(BaseModel):
    account_ids: list[str] = Field(min_length=1)
    new_apr_pct: Decimal = Field(ge=0, le=60)
    new_term_months: int = Field(gt=0, le=480)
    fee: Decimal = Field(default=D("0"), ge=0)


@router.post("/debt/consolidation-scenario")
def debt_consol(body: ConsolIn, request: Request, p: Principal = Cust, as_of: date = Depends(as_of_param)):
    return run(p, lambda c: debt_f.consolidation_scenario(_snap(c, p, as_of), body.account_ids, body.new_apr_pct, body.new_term_months, body.fee), request=request)


# ---------------------------------------------------------------- fraud / consents
@router.get("/anomaly-events")
def anomaly_events(request: Request, p: Principal = Cust):
    return {"events": run(p, fraud_f.list_events, request=request),
            "note": "Anomalies are unusual activity for review. They are not confirmed fraud."}


class FraudCaseIn(BaseModel):
    transaction_id: str | None = None
    reason: str = Field(min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    share_context: bool = False


@router.post("/fraud/cases", status_code=201)
def fraud_case_create(body: FraudCaseIn, request: Request, p: Principal = Cust):
    return run(p, lambda c: fraud_f.create_case(c, p.actor_id, body.transaction_id, body.reason, body.description, body.share_context), request=request)


@router.get("/fraud/cases")
def fraud_cases(request: Request, p: Principal = Cust):
    return {"cases": _ser(run(p, fraud_f.list_cases, request=request))}


class ConsentIn(BaseModel):
    scope: str = Field(pattern="^(marketing|case_context_sharing|data_sharing)$")
    granted: bool


@router.get("/consents")
def consents_get(request: Request, p: Principal = Cust):
    return {"consents": _ser(run(p, lambda c: c.execute(text("SELECT scope, granted, updated_at FROM pnc_consents ORDER BY scope")).mappings().all(), request=request))}


@router.put("/consents")
def consents_put(body: ConsentIn, request: Request, p: Principal = Cust):
    def fn(c):
        c.execute(text("INSERT INTO pnc_consents(customer_id, scope, granted) VALUES (:c,:s,:g) "
                       "ON CONFLICT (customer_id, scope) DO UPDATE SET granted = EXCLUDED.granted, updated_at = now()"),
                  {"c": p.actor_id, "s": body.scope, "g": body.granted})
        c.execute(text("SELECT log_audit('consent.update', :s, NULL, 'allowed', CAST(:d AS jsonb))"), {"s": body.scope, "d": f'{{"granted": {str(body.granted).lower()}}}'})
        return {"scope": body.scope, "granted": body.granted}
    return run(p, fn, request=request)
