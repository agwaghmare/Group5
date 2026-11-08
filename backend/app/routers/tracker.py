"""All original tracker columns for the signed-in customer; no Lab Package adapters."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.agents.amelia import FEATURES
from app.orm.access import snapshot_dict, tracker_query
from app.orm.identity import current_identity
from app.orm.models import TRACKER_COLUMNS
from app.staff.store import now

router = APIRouter(prefix="/api/v1/pnc", tags=["Personal finance tracker"])
BANNER = "Synthetic tracker. Educational information, not financial advice. Amelia explains verified numbers only."


class Ask(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    feature_id: str
    resource_id: str | None = None
    question: str = Field(min_length=1, max_length=2000)


def snapshots(store, customer_id=None):
    rows = list(store.db.scalars(tracker_query(store, customer_id)))
    store.audit("own_finance_read", str(store.user.customer.tracker_id))
    if not rows:
        raise HTTPException(404, "No financial snapshots found")
    return rows


def as_json(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: as_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_json(item) for item in value]
    return value


def number(row, key):
    value = getattr(row, key)
    return float(value) if value is not None else None


def loan_payment(principal, annual_rate, months):
    if principal is None or months in (None, 0):
        return None
    p, n = Decimal(str(principal)), Decimal(str(months))
    r = Decimal(str(annual_rate or 0)) / Decimal(12)
    if r == 0:
        return float(p / n)
    return float(p * r / (1 - (1 + r) ** (-int(months))))


def xray_from(row):
    indicators = []
    for key, label, unit, watch, risk, high_good in [
        ("emergency_fund_months", "Emergency fund", "months", 6, 3, True),
        ("credit_utilization", "Credit utilization", "ratio", .30, .60, False),
        ("liquidity_runway_months", "Liquidity runway", "months", 3, 1, True),
        ("debt_service_coverage", "Debt service coverage", "ratio", 1.2, 1.0, True),
        ("savings_streak_months", "Savings streak", "months", 3, 1, True),
        ("budget_variance_pct", "Budget variance", "percent", 10, 20, False),
    ]:
        raw = number(row, key)
        status = ("unavailable" if raw is None else
                  ("risk" if raw < risk else "watch" if raw < watch else "ok") if high_good else
                  ("risk" if raw > risk else "watch" if raw > watch else "ok"))
        indicators.append({"id": key, "label": label, "unit": unit, "raw": raw,
                           "status": status, "watch_threshold": watch, "risk_threshold": risk,
                           "explanation": "Observed synthetic tracker value; thresholds are prototype assumptions.",
                           "source": "personal_finance_tracker_dataset.csv"})
    return {"customer_id": str(row.user_id), "as_of": row.date.isoformat() if hasattr(row.date, "isoformat") else row.date,
            "overall": {"score": None, "band": "unavailable", "indicators_used": len(indicators),
                        "indicators_total": len(indicators),
                        "disclaimer": "No invented composite score. Tracker-derived indicators only."},
            "indicators": indicators}


def allow_amelia(store, feature):
    if store.user.role_key != "customer":
        store.audit("access_denied", feature, "denied", reason="Amelia is a customer finance agent")
        raise HTTPException(403, "Amelia is only available on a customer finance account")
    if feature not in FEATURES:
        raise HTTPException(422, "Unknown Amelia feature")
    grants = store.user.role.features or []
    prefix = feature.split(".", 1)[0] + ".*"
    if feature not in grants and prefix not in grants:
        store.audit("access_denied", feature, "denied", reason="Feature not granted")
        raise HTTPException(403, "Not available for your role")


def evidence_for(feature, rows):
    latest = rows[-1]
    data = as_json(snapshot_dict(latest))
    income = number(latest, "monthly_income") or 0
    bills = number(latest, "recurring_bill_total") or 0
    subs = number(latest, "subscription_cost_monthly") or 0
    debt_pay = number(latest, "minimum_debt_payment") or 0
    available = number(latest, "available_balance") or 0
    obligations = bills + subs + debt_pay
    safe_spend = max(0, available - obligations)
    dti = (debt_pay / income) if income else None
    if feature == "fin.profile":
        return {"as_of": data["date"], "customer_id": str(latest.user_id),
                "source": "personal_finance_tracker_dataset.csv", "source_type": "synthetic_finance_tracker",
                "checking_balance": data["checking_balance"], "savings_balance": data["savings_balance"],
                "available_balance": data["available_balance"], "portfolio_value": data["portfolio_value"],
                "home_equity": data["home_equity"], "total_debt_balance": data["total_debt_balance"],
                "monthly_income": data["monthly_income"], "pay_frequency": data["pay_frequency"]}
    if feature == "fin.investments":
        return {"as_of": data["date"], "portfolio_value": data["portfolio_value"],
                "equity_allocation_pct": data["equity_allocation_pct"],
                "investment_volatility": data["investment_volatility"],
                "retirement_contribution": data["retirement_contribution"],
                "limitation": "Recorded synthetic tracker only; current slider scenarios are not included in this explanation."}
    if feature == "fin.xray":
        return xray_from(latest)
    if feature == "fin.futureyou":
        principal = 30000 - 5000
        payment = loan_payment(principal, 0.08, 60)
        return {"as_of": data["date"], "projected_balance_30d": data["projected_balance_30d"],
                "emergency_fund_months": data["emergency_fund_months"],
                "liquidity_runway_months": data["liquidity_runway_months"],
                "available_balance": data["available_balance"], "monthly_income": data["monthly_income"],
                "hypothetical_car": {"label": "workshop_example", "price": 30000, "down_payment": 5000,
                                     "apr": 8, "term_months": 60, "principal": principal,
                                     "monthly_payment": payment,
                                     "limitation": "Taxes, insurance, maintenance and fees are omitted."}}
    if feature == "fin.moneymission":
        return {"as_of": data["date"], "savings_balance": data["savings_balance"],
                "emergency_fund_months": data["emergency_fund_months"],
                "monthly_savings_contribution": data["monthly_savings_contribution"],
                "savings_apy": data["savings_apy"], "available_balance": available,
                "known_obligations": obligations, "safe_spend": safe_spend,
                "safe_spend_formula": "available_balance minus recurring bills, subscriptions and minimum debt payment"}
    if feature == "fin.immune":
        return {"as_of": data["date"], "monthly_income": data["monthly_income"],
                "income_volatility_3m": data["income_volatility_3m"],
                "overdraft_count_90d": data["overdraft_count_90d"],
                "liquidity_runway_months": data["liquidity_runway_months"],
                "life_event_type": data["life_event_type"],
                "emergency_fund_months": data["emergency_fund_months"],
                "known_obligations": obligations}
    if feature == "fin.moneyleaks":
        return {"as_of": data["date"], "recurring_bill_total": data["recurring_bill_total"],
                "subscription_cost_monthly": data["subscription_cost_monthly"],
                "budget_variance_pct": data["budget_variance_pct"],
                "bill_payment_delay_count": data["bill_payment_delay_count"],
                "monthly_income": data["monthly_income"]}
    if feature == "fin.debt":
        return {"as_of": data["date"], "total_debt_balance": data["total_debt_balance"],
                "minimum_debt_payment": data["minimum_debt_payment"],
                "weighted_avg_apr": data["weighted_avg_apr"],
                "remaining_loan_term_months": data["remaining_loan_term_months"],
                "credit_utilization": data["credit_utilization"],
                "credit_limit_total": data["credit_limit_total"],
                "mortgage_balance": data["mortgage_balance"],
                "debt_service_coverage": data["debt_service_coverage"],
                "dti": dti, "monthly_income": data["monthly_income"]}
    if feature == "fin.rewards":
        return {"status": "missing_reward_rules",
                "message": "Rewards Compare uses only user-entered reward rules. None are stored for this account."}
    if feature == "fin.fraud":
        return {"as_of": data["date"], "unusual_merchant_flag": data.get("unusual_merchant_flag"),
                "transaction_amount_zscore": data.get("transaction_amount_zscore"),
                "transaction_velocity_24h": data.get("transaction_velocity_24h"),
                "overdraft_count_90d": data["overdraft_count_90d"],
                "late_payments_12m": data["late_payments_12m"],
                "disclaimer": "Synthetic flags only. Not an accusation and not a filed claim."}
    if feature == "fin.coach":
        return {"as_of": data["date"], "checking_balance": data["checking_balance"],
                "savings_balance": data["savings_balance"], "available_balance": data["available_balance"],
                "monthly_income": data["monthly_income"], "recurring_bill_total": data["recurring_bill_total"],
                "subscription_cost_monthly": data["subscription_cost_monthly"],
                "total_debt_balance": data["total_debt_balance"], "emergency_fund_months": data["emergency_fund_months"],
                "projected_balance_30d": data["projected_balance_30d"], "safe_spend": safe_spend}
    if feature == "fin.modellab":
        return {"status": "not_configured",
                "message": "Model Lab is not wired for this customer session. No comparison run is available."}
    return {"as_of": data["date"]}


@router.get("/profile")
def profile(customer_id: str | None = None, store=Depends(current_identity)):
    latest = snapshots(store, customer_id)[-1]
    return {**snapshot_dict(latest), "customer_id": str(latest.user_id),
            "email": store.user.email, "role": store.user.role_key,
            "source_type": "synthetic_finance_tracker", "source": "personal_finance_tracker_dataset.csv"}


@router.get("/tracker")
@router.get("/tracker/snapshots")
def tracker(customer_id: str | None = None, limit: int = Query(default=100, ge=1, le=1000), store=Depends(current_identity)):
    rows = snapshots(store, customer_id)
    return {"customer_id": str(rows[0].user_id), "columns": TRACKER_COLUMNS,
            "snapshots": [snapshot_dict(r) for r in rows[-limit:]], "total": len(rows),
            "source": "personal_finance_tracker_dataset.csv", "synthetic": True}


@router.get("/financial-xray")
def xray(store=Depends(current_identity)):
    row = snapshots(store)[-1]
    return xray_from(row)


@router.get("/cash-flow")
def cash_flow(store=Depends(current_identity)):
    rows = snapshots(store)
    return {"months": [{"month": r.date, "income": r.monthly_income,
                        "recurring_bill_total": r.recurring_bill_total,
                        "minimum_debt_payment": r.minimum_debt_payment,
                        "monthly_savings_contribution": r.monthly_savings_contribution} for r in rows],
            "source": "synthetic tracker; actual transactions are not available"}


@router.get("/accounts")
def accounts(store=Depends(current_identity)):
    row = snapshots(store)[-1]
    return {"accounts": [], "status": "aggregate_data_only", "as_of": row.date,
            "balances": {k: getattr(row, k) for k in ("checking_balance", "savings_balance", "total_debt_balance", "mortgage_balance", "portfolio_value")},
            "message": "The tracker contains aggregate balances; individual account records are not present."}


@router.post("/assistant")
def assistant(body: Ask, store=Depends(current_identity)):
    allow_amelia(store, body.feature_id)
    rows = snapshots(store)
    evidence = evidence_for(body.feature_id, rows)
    from app.agents.amelia import AgentError, explain
    from app.orm.models import AuthSession, User
    original_role, user_id = store.user.role_key, store.user.id
    token_digest = store.auth_token_digest
    store.db.commit()
    try:
        result = explain(body.question, original_role, body.feature_id, evidence)
    except AgentError as exc:
        store.audit("assistant_failed", body.feature_id, "failed", status=exc.status)
        raise HTTPException(exc.status, exc.message) from None
    store.db.expire_all()
    current = store.db.get(User, user_id)
    auth = store.db.get(AuthSession, token_digest)
    if not current or not current.active or not auth or auth.payload["expires_at"] <= now():
        store.audit("access_denied", "assistant", "denied", reason="Session expired during Amelia request")
        raise HTTPException(401, "Your session expired during the request")
    if current.role_key != original_role:
        store.audit("access_denied", "assistant", "denied", reason="Role changed during Amelia request")
        raise HTTPException(403, "Your role changed. Refresh your workspace.")
    from app.orm.identity import set_identity
    set_identity(store, current)
    allow_amelia(store, body.feature_id)
    store.audit("assistant_answer", str(store.user.customer.tracker_id), feature=body.feature_id,
                model=result["model"], prompt_version=result["prompt_version"])
    return {**result, "agent": "Amelia", "evidence": evidence, "synthetic": True, "banner": BANNER,
            "trace": ["role_gate", "own_tracker_evidence", "deterministic_compute", "mistral_explain", "evidence_validation"]}
