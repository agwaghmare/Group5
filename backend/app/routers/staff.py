"""Employee API. See /docs and backend/EMPLOYEE_API.md for frontend integration."""
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from app.orm.identity import current_identity, find_user, issue_session, public_user
from app.staff.policy import ALLOWED, OUTCOMES, evaluate
from app.staff.registry import BANNER, FEATURES, ROLES, capabilities, visible
from app.staff.seed import business_date, tenure_months
from app.staff.store import Store, digest, ident, now

router = APIRouter(prefix="/staff", tags=["Synthetic employee workspace"])


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class Login(Body):
    employee_id: str


class Grant(Body):
    prospect_id: str
    purpose: Literal["application_review", "senior_review", "quality_review"]
    reference_id: str = Field(min_length=3, max_length=100)
    break_glass_reason: str | None = Field(default=None, min_length=10, max_length=1000)


class Run(Body):
    grant_id: str


class Decision(Body):
    run_id: str
    decision: Literal["Proceed to next step (simulated)", "Request more information", "Refer to senior review", "Decline as entered (with reason codes)"]
    rationale: str = Field(min_length=10, max_length=2000)
    override_reason: str | None = Field(default=None, min_length=10, max_length=2000)


class CaseChange(Body):
    status: Literal["assigned", "in_progress", "resolved"]
    note: str = Field(min_length=3, max_length=2000)


class Redemption(Body):
    item_id: str
    quantity: int = Field(ge=1, le=2)
    request_id: str = Field(min_length=8, max_length=100)


class BenefitRules(Body):
    annual_cap_cents: int = Field(ge=0, le=1000000)
    quarterly_item_limit: int = Field(ge=1, le=2)
    rates: tuple[int, int, int] = (10, 15, 20)


class Item(Body):
    item_key: str = Field(pattern=r"^[A-Z0-9-]{1,30}$")
    name: str = Field(min_length=3, max_length=100)
    category: Literal["accessory", "parts", "service", "merchandise"]
    list_price_cents: int = Field(ge=1, le=10000000)
    discount_eligible: bool = True


class Ask(Body):
    feature_id: str
    resource_id: str | None = None
    question: str = Field(min_length=1, max_length=2000)


class Campaign(Body):
    name: str = Field(min_length=3, max_length=100)


def database():
    with Store() as store:
        yield store


def fail(store, message, resource="", status=403):
    store.audit("access_denied", resource, "denied", reason=message)
    raise HTTPException(status, message)


def demo_enabled():
    if os.environ.get("APP_ENV", "dev") == "prod" or os.environ.get("STAFF_DEMO_ENABLED", "false").lower() != "true":
        raise HTTPException(404, "Demo persona login is disabled")


def session(store=Depends(current_identity)):
    if store.user.role_key == "customer":
        fail(store, "Employee access is not available for your role", "staff")
    return store


def allow(store, feature, write=False):
    from app.orm.authorization import require_feature
    require_feature(store, feature, write)
    store.audit("feature_access", feature)



def assigned(store, table, key):
    row = store.get(table, key)
    if not row:
        fail(store, "Resource not found or unavailable for your role", key, 404)
    return row


def prospect_for_grant(store, key):
    from app.orm.authorization import require_feature
    from app.orm.models import Prospect
    require_feature(store, "staff.creditresearch")
    row = store.db.get(Prospect, key)
    if not row:
        fail(store, "Prospect not found", key, 404)
    return {k: row.payload[k] for k in ("id", "assigned_to", "application_ref", "product")}


def grant_for(store, grant_id, prospect_id=None):
    grant = assigned(store, "grants", grant_id)
    if (grant["employee_id"] != store.employee["id"] or grant["expires_at"] <= now()
            or (prospect_id and grant["prospect_id"] != prospect_id)):
        fail(store, "Research grant expired or does not cover this resource", grant_id)
    return grant


def public_prospect(row):
    # Notes, name, age, location and protected labels never enter analyst payloads.
    return {key: value for key, value in row.items() if key in ALLOWED or key in
            ("id", "application_ref", "assigned_to", "synthetic", "as_of", "employment_months", "delinquencies_12m", "bankruptcy_years_ago")}


def run_for(store, key):
    row = store.get("runs", key)
    if not row:
        fail(store, "Run unavailable for this analyst", key)
    if row["employee_id"] != store.employee["id"]:
        fail(store, "Research run belongs to another analyst", key)
    grant_for(store, row["grant_id"], row["prospect_id"])
    return row


def benefit_rules(store):
    return max(store.all("benefit_rules"), key=lambda x: x["version"])


def active_catalog(store):
    latest = {}
    for row in store.all("catalog"):
        key = row["item_key"]
        if key not in latest or row["version"] > latest[key]["version"]:
            latest[key] = row
    return list(latest.values())


def benefit_summary(store):
    rules = benefit_rules(store)
    today = business_date()
    months = tenure_months(store.employee["hire_date"], today)
    tier = max((t for t in rules["tiers"] if months >= t["min_months"]), key=lambda t: t["min_months"])
    ledger = [r for r in store.all("redemptions") if r["employee_id"] == store.employee["id"]]
    used = sum(r["discount_cents"] for r in ledger if r["redeemed_at"][:4] == str(today.year))
    return {"tenure_months": months, "discount_rate_percent": tier["rate"], "rules": rules,
            "annual_discount_used_cents": used, "remaining_cap_cents": max(0, rules["annual_cap_cents"] - used),
            "ledger": ledger, "as_of": today.isoformat(), "synthetic": True}


@router.get("/demo/personas")
def personas(store=Depends(database)):
    demo_enabled()
    return {"synthetic_demo": True, "personas": [
        {k: r[k] for k in ("id", "role", "display_name", "synthetic")} for r in store.all("employees")]}


@router.post("/demo/session", status_code=201)
def login(body: Login, store=Depends(database)):
    demo_enabled()
    employee = store.get("employees", body.employee_id)
    if not employee or employee["status"] != "active":
        fail(store, "Unknown demo persona", body.employee_id, 404)
    user = find_user(store, employee["id"])
    if not user or not user.active:
        fail(store, "Inactive user", employee["id"], 401)
    issued = issue_session(store, user)
    return {**issued, "employee": employee, "tabs": visible(user.role_key),
            "features": capabilities(user.role_key), "banner": BANNER}



@router.delete("/session", status_code=204)
def logout(authorization: str = Header(), store=Depends(session)):
    # Explicit endpoint policy permits revoking only the presented bearer token.
    store.execute(f"DELETE FROM {store.table('sessions')} WHERE id=%s", (digest(authorization.removeprefix("Bearer ")),))
    store.audit("logout")
    return Response(status_code=204)


@router.get("/me")
def me(store=Depends(session)):
    store.audit("session_profile_read")
    return {"employee": store.employee, "tabs": store.user.role.tabs,
            "features": store.user.role.features, "banner": BANNER,
            "storage": "sqlalchemy_sqlite", "user": public_user(store.user),
            "agent_provider": "mistral" if os.environ.get("MISTRAL_API_KEY") else "unconfigured", "synthetic_demo": store.user.synthetic}


@router.get("/registry")
def registry(store=Depends(session)):
    allow(store, "staff.access")
    return {"role": store.employee["role"], "tabs": [
        {"key": key, "position": i+1} for i, key in enumerate(visible(store.employee["role"]))],
        "features": capabilities(store.employee["role"]), "banner": BANNER}


@router.get("/home")
def home(store=Depends(session)):
    allow(store, "staff.access")
    role = store.employee["role"]
    counts = {}
    if role == "credit_analyst":
        counts["assigned_prospects"] = sum(r["assigned_to"] == store.employee["id"] for r in store.all("prospects"))
    elif role == "service_specialist":
        counts["open_cases"] = sum(r["assigned_to"] == store.employee["id"] and r["status"] != "resolved" for r in store.all("cases"))
    elif role in ("compliance_analyst", "auditor"):
        counts["audit_events"] = len(store.all("audit"))
    return {"greeting": f"Welcome, {store.employee['display_name']}", "role": role,
            "counts": counts, "banner": BANNER, "as_of": now()}


@router.get("/prospects")
def prospect_queue(store=Depends(session)):
    allow(store, "staff.prospect")
    rows = [r for r in store.all("prospects") if r["assigned_to"] == store.employee["id"]]
    # Queue metadata only. The purpose gate must precede any credit-file read.
    return {"prospects": [{k: r[k] for k in ("id", "product", "application_ref", "assigned_to", "as_of", "synthetic")} for r in rows],
            "blind_review": True, "masked_fields": ["name", "age", "city"], "requires_access_grant": True}


@router.post("/access-grants", status_code=201)
def access_grant(body: Grant, store=Depends(session)):
    allow(store, "staff.creditresearch")
    prospect = prospect_for_grant(store, body.prospect_id)
    conflict = any(r["employee_id"] == store.employee["id"] and r["prospect_id"] == prospect["id"] for r in store.all("links"))
    if conflict:
        fail(store, "Conflict of interest: another analyst must handle this prospect", prospect["id"])
    outside = prospect["assigned_to"] != store.employee["id"]
    if outside and not body.break_glass_reason:
        fail(store, "Outside assignment: typed break-glass reason required", prospect["id"])
    if body.reference_id != prospect["application_ref"]:
        fail(store, "Application reference does not match", prospect["id"], 422)
    grant = {"id": ident("G"), **body.model_dump(), "employee_id": store.employee["id"],
        "created_at": now(), "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=int(os.environ.get("STAFF_GRANT_MINUTES", "15")))).isoformat()}
    store.insert("grants", grant, store.employee["id"])
    store.audit("research_access_granted", prospect["id"], purpose=body.purpose,
                grant_id=grant["id"], break_glass=outside, reason=body.break_glass_reason)
    return grant


@router.get("/prospects/{prospect_id}")
def prospect_detail(prospect_id: str, grant_id: str, store=Depends(session)):
    allow(store, "staff.prospect")
    grant_for(store, grant_id, prospect_id)
    row = assigned(store, "prospects", prospect_id)
    row = {**row, **assigned(store, "credit_profiles", prospect_id)}
    store.audit("credit_file_read", prospect_id, grant_id=grant_id)
    return {"prospect": public_prospect(row), "masked_fields": ["name", "age", "city"], "blind_review": True}


@router.get("/policies/current")
def policy(store=Depends(session)):
    if store.employee["role"] not in ("credit_analyst", "compliance_analyst", "auditor"):
        fail(store, "Not available for your role", "policies")
    store.audit("policy_read")
    return store.get("policies", "pnc-demo-v1")


@router.post("/research-runs", status_code=201)
def research(body: Run, store=Depends(session)):
    allow(store, "staff.creditresearch")
    grant = grant_for(store, body.grant_id)
    prospect = assigned(store, "prospects", grant["prospect_id"])
    prospect = {**prospect, **assigned(store, "credit_profiles", grant["prospect_id"])}
    result = evaluate(prospect, store.get("policies", "pnc-demo-v1"))
    row = {"id": ident("RUN"), **result, "prospect_id": prospect["id"],
           "employee_id": store.employee["id"], "grant_id": grant["id"],
           "run_at": now(), "data_as_of": prospect["as_of"]}
    store.insert("runs", row, store.employee["id"])
    store.audit("research_run", row["id"], grant_id=grant["id"], purpose=grant["purpose"],
                policy_version=result["policy_version"], break_glass=bool(grant["break_glass_reason"]))
    return row


@router.get("/research-runs/{run_id}")
def read_run(run_id: str, store=Depends(session)):
    allow(store, "staff.creditresearch")
    row = run_for(store, run_id)
    store.audit("research_run_read", run_id)
    return row


@router.post("/decisions", status_code=201)
def decision(body: Decision, store=Depends(session)):
    allow(store, "staff.decision", write=True)
    run = run_for(store, body.run_id)
    if any(r["run_id"] == run["id"] for r in store.all("decisions")):
        raise HTTPException(409, "A human decision is already recorded for this run")
    override = body.decision != OUTCOMES[run["outcome"]]
    if override and not body.override_reason:
        raise HTTPException(422, "Typed override reason is required")
    row = {"id": ident("DEC"), **body.model_dump(), "employee_id": store.employee["id"],
           "override": override, "review_required": override, "recorded_at": now(),
           "reason_codes": [r["reason_code"] for r in run["rules"] if r["status"] != "pass"],
           "synthetic": True, "sent_externally": False}
    store.insert("decisions", row, store.employee["id"])
    store.audit("human_decision", row["id"], override=override, grant_id=run["grant_id"])
    return row


@router.get("/decisions")
def decisions(store=Depends(session)):
    allow(store, "staff.decision")
    rows = store.all("decisions")
    if store.employee["role"] == "credit_analyst":
        rows = [r for r in rows if r["employee_id"] == store.employee["id"]]
    store.audit("decision_log_read")
    return {"decisions": rows}


@router.get("/cases")
def cases(store=Depends(session)):
    allow(store, "staff.cases")
    rows = [r for r in store.all("cases") if r["assigned_to"] == store.employee["id"]]
    store.audit("case_queue_read")
    return {"cases": rows}


@router.get("/cases/{case_id}")
def case_detail(case_id: str, store=Depends(session)):
    allow(store, "staff.cases")
    row = assigned(store, "cases", case_id)
    if row["assigned_to"] != store.employee["id"]:
        fail(store, "Case is not assigned to you", case_id)
    store.audit("case_read", case_id)
    return {"case": row, "brief": {"situation": row["consented_context"],
            "questions_to_ask": ["Which obligations are most urgent?", "What context may we share for follow-up?"],
            "tradeoffs": "Review available support with a human; no offer is promised.",
            "provider": "mock", "human_review_required": True, "upsell_allowed": False},
            "events": [e for e in store.all("case_events") if e["case_id"] == case_id]}


@router.patch("/cases/{case_id}")
def update_case(case_id: str, body: CaseChange, store=Depends(session)):
    allow(store, "staff.cases")
    row = assigned(store, "cases", case_id)
    if row["assigned_to"] != store.employee["id"]:
        fail(store, "Case is not assigned to you", case_id)
    transitions = {"new": {"assigned", "in_progress"}, "assigned": {"in_progress"},
                   "in_progress": {"in_progress", "resolved"}, "resolved": set()}
    if body.status not in transitions[row["status"]]:
        raise HTTPException(409, "Invalid case status transition")
    event = {"id": ident("EV"), "case_id": case_id, **body.model_dump(),
             "employee_id": store.employee["id"], "ts": now()}
    store.insert("case_events", event, store.employee["id"])
    store.update("cases", {**row, "status": body.status})
    store.audit("case_updated", case_id)
    return event


@router.get("/benefits")
def benefits(store=Depends(session)):
    allow(store, "staff.benefits")
    store.audit("own_benefits_read")
    return {**benefit_summary(store), "catalog": active_catalog(store),
            "redemption_label": "Simulated redemption. Nothing was purchased."}


@router.post("/benefits/redemptions", status_code=201)
def redeem(body: Redemption, store=Depends(session)):
    allow(store, "staff.benefits")
    summary = benefit_summary(store)
    prior = next((r for r in summary["ledger"] if r["request_id"] == body.request_id), None)
    if prior:
        if prior["item_key"] != body.item_id or prior["quantity"] != body.quantity:
            raise HTTPException(409, "Idempotency key was already used for a different redemption")
        return prior
    item = next((r for r in active_catalog(store) if r["item_key"] == body.item_id), None)
    if not item or not item["discount_eligible"]:
        raise HTTPException(422, "Item is not eligible")
    today = business_date()
    quarter = (today.month - 1) // 3
    count = sum(r["quantity"] for r in summary["ledger"] if r["item_key"] == body.item_id
                and datetime.fromisoformat(r["redeemed_at"]).year == today.year
                and (datetime.fromisoformat(r["redeemed_at"]).month - 1) // 3 == quarter)
    allowed = max(0, summary["rules"]["quarterly_item_limit"] - count)
    if body.quantity > allowed:
        raise HTTPException(409, {"message": "Quarterly per-item limit exceeded", "allowed_quantity": allowed})
    if not summary["remaining_cap_cents"]:
        raise HTTPException(409, "Annual discount cap reached")
    total = item["list_price_cents"] * body.quantity
    discount = min(int((Decimal(total) * Decimal(summary["discount_rate_percent"]) / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)), summary["remaining_cap_cents"])
    row = {"id": ident("RED"), **body.model_dump(), "item_key": item["item_key"],
           "employee_id": store.employee["id"], "list_price_cents": total,
           "discount_cents": discount, "discounted_price_cents": total-discount,
           "remaining_cap_cents": summary["remaining_cap_cents"]-discount,
           "rule_version": summary["rules"]["version"], "catalog_version": item["version"],
           "rate_percent": summary["discount_rate_percent"], "redeemed_at": now(),
           "voucher": ident("DEMO-VOUCHER"), "synthetic": True,
           "label": "Simulated redemption. Nothing was purchased."}
    store.insert("redemptions", row, store.employee["id"])
    store.audit("simulated_redemption", row["id"])
    return row


def benefits_admin(store):
    allow(store, "staff.benefits")
    if store.employee["role"] != "benefits_admin":
        fail(store, "Benefits administrator required", "benefits")


@router.get("/benefits/admin/usage")
def benefit_usage(store=Depends(session)):
    benefits_admin(store)
    rows = store.all("redemptions")
    store.audit("benefits_admin_usage_read")
    return {"ledger": rows, "redemptions": len(rows), "discount_cents": sum(r["discount_cents"] for r in rows)}


@router.post("/benefits/admin/rules", status_code=201)
def new_benefit_rules(body: BenefitRules, store=Depends(session)):
    benefits_admin(store)
    if any(r < 0 or r > 100 for r in body.rates):
        raise HTTPException(422, "Rates must be between zero and 100")
    version = benefit_rules(store)["version"] + 1
    row = {"id": f"benefits-v{version}", "version": version,
           "tiers": [{"min_months": months, "rate": rate} for months, rate in zip([0, 12, 60], body.rates)],
           "annual_cap_cents": body.annual_cap_cents, "quarterly_item_limit": body.quarterly_item_limit,
           "synthetic": True, "created_at": now()}
    store.insert("benefit_rules", row)
    store.audit("benefit_rules_version_created", row["id"])
    return row


@router.post("/benefits/admin/catalog", status_code=201)
def new_catalog_item(body: Item, store=Depends(session)):
    benefits_admin(store)
    prior = [r for r in store.all("catalog") if r["item_key"] == body.item_key]
    version = max((r["version"] for r in prior), default=0)+1
    row = {**body.model_dump(), "id": f"{body.item_key}-v{version}", "version": version, "synthetic": True}
    store.insert("catalog", row)
    store.audit("catalog_version_created", row["id"])
    return row


@router.get("/audit")
def audit(action: str | None = None, outcome: str | None = None, actor: str | None = None,
          resource: str | None = None, limit: int = 100, store=Depends(session)):
    allow(store, "staff.audit")
    if not 1 <= limit <= 500:
        raise HTTPException(422, "Limit must be 1 to 500")
    store.audit("audit_log_read")
    rows = [r for r in store.all("audit") if all(v is None or r.get(k) == v for k, v in
            (("action", action), ("outcome", outcome), ("actor", actor), ("resource", resource))) ]
    return {"events": sorted(rows, key=lambda r: r["ts"], reverse=True)[:limit], "append_only": True}


def aggregate_research(store):
    from app.orm.metrics import research_metrics
    return research_metrics(store)



@router.get("/portfolio")
def portfolio(store=Depends(session)):
    allow(store, "staff.portfolio")
    store.audit("portfolio_aggregate_read")
    if store.employee["role"] == "marketing_analyst":
        rows = store.all("campaigns")
        return {"scope": "campaign_results_only", "campaign_count": len(rows) if len(rows) >= 5 else None,
                "suppression_threshold": 5, "suppression_notice": "Groups smaller than five are suppressed.",
                "sends": "simulated"}
    from sqlalchemy import func, select
    from app.orm.models import FinanceSnapshot
    latest = select(FinanceSnapshot.user_id, func.max(FinanceSnapshot.date).label("latest_date")).group_by(FinanceSnapshot.user_id).subquery()
    query = select(FinanceSnapshot).join(latest, (FinanceSnapshot.user_id == latest.c.user_id) & (FinanceSnapshot.date == latest.c.latest_date))
    rows = list(store.db.scalars(query))
    n = len(rows)
    metrics = {key: round(sum(float(getattr(r, key)) for r in rows if getattr(r, key) is not None) /
                         sum(getattr(r, key) is not None for r in rows), 2)
               if sum(getattr(r, key) is not None for r in rows) >= 5 else None
               for key in ("monthly_income", "total_debt_balance", "emergency_fund_months")}
    return {"customer_count": n if n >= 5 else None, "mean_metrics": metrics,
            "source": "SQLAlchemy finance_snapshots, imported from personal_finance_tracker_dataset.csv",
            "data_as_of": max((r.date.isoformat() for r in rows), default=None),
            "research": aggregate_research(store), "synthetic": True}



@router.get("/compliance/reviews")
def reviews(store=Depends(session)):
    if store.employee["role"] != "compliance_analyst":
        fail(store, "Compliance analyst required", "reviews")
    store.audit("override_review_queue_read")
    return {"overrides": [r for r in store.all("decisions") if r["override"]],
            "research": [{k: r[k] for k in ("id", "policy_version", "run_at", "outcome", "rules", "validation")}
                         for r in store.all("runs")]}


@router.get("/compliance/fairness")
def fairness(store=Depends(session)):
    allow(store, "staff.fairness")
    store.audit("fairness_metrics_read")
    from app.orm.metrics import fairness_metrics
    measured = fairness_metrics(store)
    reference = measured.get("A", {}).get("meets_policy_rate", 0)
    metrics = []
    for label, value in measured.items():
        ratio = value["meets_policy_rate"]/reference if reference else None
        metrics.append({"group": label, **value, "ratio_to_A": ratio,
                        "review": ratio < .8 if ratio is not None else None})
    # Offline seed invariance check: protected fields cannot change engine input.
    from app.staff.seed import prospects
    pair = prospects()[-2:]
    a, b = (evaluate(p) for p in pair)
    invariance = a["outcome"] == b["outcome"] and a["input_hash"] == b["input_hash"]
    return {"groups": metrics, "reference_group": "A", "invariance_passed": invariance,
            "policy_version": "pnc-demo-v1", "pair": ["P029", "P030"], "measured_at": now(),
            "label": "Illustrative synthetic screening, not a legal standard. Empty groups mean no recorded runs."}


@router.get("/campaigns/audience")
def audience(store=Depends(session)):
    allow(store, "staff.campaigns")
    store.audit("marketing_audience_read")
    # Finance tracker has no consent/vulnerability/channel columns. Fail closed.
    return {"audience": [], "status": "missing_consent_source",
            "message": "The finance tracker lacks marketing consent, vulnerability and preferred-channel records. No eligible audience can be established.",
            "required_fields": ["marketing_consent", "vulnerable_flag", "preferred_channel"],
            "masked_fields": ["customer_id", "income"], "sends": "simulated_only"}


@router.post("/campaigns", status_code=201)
def campaign(body: Campaign, store=Depends(session)):
    allow(store, "staff.campaigns")
    raise HTTPException(409, "No verified consent-filtered audience is available; no campaign was created or sent")


@router.get("/compliance/anomalies")
def anomalies(store=Depends(session)):
    allow(store, "staff.anomaly")
    return {"anomalies": [], "status": "awaiting_fin_fraud_source",
            "message": "fin.fraud has no connected detection feed. No detections have been invented."}


@router.post("/assistant")
def assistant(body: Ask, store=Depends(session)):
    allow(store, body.feature_id)
    evidence = {}
    if body.feature_id == "learn.explain" and body.resource_id:
        if store.employee["role"] == "credit_analyst":
            row = run_for(store, body.resource_id)
        elif store.employee["role"] == "compliance_analyst":
            row = assigned(store, "runs", body.resource_id)
        else:
            fail(store, "Credit evidence explanations are not available for your role", body.resource_id)
        evidence = {"run_id": row["id"], "policy_version": row["policy_version"],
                    "rules": [r for r in row["rules"] if r["rule"] in ("dti", "utilization")]}
        answer = ("Debt-to-income is existing monthly debt plus the proposed monthly payment, divided by monthly income. "
                  "Credit utilization is revolving balance divided by revolving credit limit. "
                  "The attached rule evidence shows the recorded value and synthetic policy threshold.")
    elif body.feature_id in ("staff.creditresearch", "staff.prospect"):
        if not body.resource_id:
            raise HTTPException(422, "A research run ID is required")
        row = run_for(store, body.resource_id)
        evidence = {k: row[k] for k in ("id", "outcome", "rules", "missing_inputs", "counterfactuals", "policy_version")}
        answer = f"The recorded review outcome is {row['outcome']}. Code evaluated the stored synthetic policy; a human must record the decision."
    elif body.feature_id == "staff.cases":
        if not body.resource_id:
            raise HTTPException(422, "A case ID is required")
        row = assigned(store, "cases", body.resource_id)
        if row["assigned_to"] != store.employee["id"]:
            fail(store, "Case is not assigned to you", row["id"])
        evidence = {"id": row["id"], "consented_context": row["consented_context"]}
        answer = "Review the consented context and ask which obligations are most urgent. Human review is required; no offer is promised."
    elif body.feature_id in ("staff.benefits", "learn.explain"):
        summary = benefit_summary(store)
        evidence = {k: summary[k] for k in ("discount_rate_percent", "remaining_cap_cents", "rules")}
        answer = "Benefits use tenure-based discounts, an annual discount cap and a quarterly item limit. Discounted price equals list price minus the allowed discount."
    elif body.feature_id == "staff.portfolio":
        evidence = portfolio(store)
        answer = "Only aggregates allowed for your role are available. Groups smaller than five are suppressed."
    elif body.feature_id == "staff.audit":
        evidence = {"events": audit(limit=20, store=store)["events"]}
    elif body.feature_id == "staff.fairness":
        evidence = fairness(store)
    elif body.feature_id == "staff.decision":
        evidence = {"decisions": decisions(store)["decisions"][-20:]}
    elif body.feature_id == "staff.campaigns":
        evidence = audience(store)
    elif body.feature_id == "staff.anomaly":
        evidence = anomalies(store)
    elif body.feature_id == "staff.access":
        evidence = {"role": store.user.role_key, "tabs": store.user.role.tabs, "features": store.user.role.features}
    else:
        answer = "Use the role-scoped workspace endpoints for this feature. Mock Bessie does not interpret free text or perform mutations."
    from app.agents.bessie import AgentError, explain
    from app.orm.models import AuthSession, User
    original_role, user_id = store.user.role_key, store.user.id
    token_digest = store.auth_token_digest
    # Do not hold SQLite's write lock across a network request.
    store.db.commit()
    try:
        result = explain(body.question, original_role, body.feature_id, evidence)
    except AgentError as exc:
        store.audit("assistant_failed", body.resource_id or body.feature_id, "failed", status=exc.status)
        raise HTTPException(exc.status, exc.message) from None
    store.db.expire_all()
    current = store.db.get(User, user_id)
    auth = store.db.get(AuthSession, token_digest)
    if not current or not current.active or not auth or auth.payload["expires_at"] <= now():
        fail(store, "Your session expired during the request", "assistant", 401)
    if current.role_key != original_role:
        fail(store, "Your role changed. Refresh your workspace.", "assistant")
    from app.orm.identity import set_identity
    set_identity(store, current)
    allow(store, body.feature_id)
    if body.resource_id and (body.feature_id in ("staff.creditresearch", "staff.prospect") or
                            (body.feature_id == "learn.explain" and original_role == "credit_analyst")):
        run_for(store, body.resource_id)
    if body.feature_id == "staff.cases":
        assigned(store, "cases", body.resource_id)
    store.audit("assistant_answer", body.resource_id or body.feature_id, feature=body.feature_id,
                model=result["model"], prompt_version=result["prompt_version"])
    return {**result, "agent": "Wilbur" if body.feature_id == "learn.explain" else "Bessie",
            "evidence": evidence, "synthetic": True, "banner": BANNER,
            "trace": ["role_gate", "scoped_evidence", "deterministic_compute", "mistral_explain", "evidence_validation"]}
