"""One server-side row/field policy for employee records and agent evidence."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import exists, select

from app.orm.models import RECORD_MODELS, AccessGrant
from app.staff.registry import FEATURES


def deny(store, resource):
    store.audit("access_denied", resource, "denied", reason="Record scope denied")
    raise HTTPException(403, "Not available for your role or assignment")


def require_feature(store, feature, write=False):
    user = store.user
    if not user or user.role_key not in FEATURES.get(feature, []):
        deny(store, feature)
    # Database and code registry must agree; stale grants fail closed.
    if feature not in user.role.features:
        deny(store, feature)
    if feature == "staff.decision" and write and user.role_key != "credit_analyst":
        deny(store, feature)


def scoped_query(store, table):
    model = RECORD_MODELS[table]
    query = select(model)
    if not store.user:
        return query  # Bootstrap/login internals only, before identity resolution.
    role, uid = store.user.role_key, store.user.id
    eid = store.user.employee_id
    if table == "sessions":
        return query.where(model.user_id == uid)
    if role == "customer":
        deny(store, table)
    if table in ("catalog", "benefit_rules", "permissions"):
        return query
    if table == "employees":
        return query.where(model.id == eid)
    if table == "redemptions":
        return query if role == "benefits_admin" else query.where(model.owner == eid)
    if table in ("grants", "links") and role == "credit_analyst":
        return query.where(model.owner == eid)
    if table in ("prospects", "credit_profiles") and role == "credit_analyst":
        grant = exists(select(AccessGrant.id).where(
            AccessGrant.employee_id == eid, AccessGrant.prospect_id == model.id,
            AccessGrant.expires_at > datetime.now(timezone.utc).isoformat()))
        return query.where((model.owner == eid) | grant) if table == "prospects" else query.where(grant)
    if table == "runs" and role == "credit_analyst":
        # Ownership checked centrally; endpoints also require an unexpired purpose grant.
        return query.where(model.owner == eid)
    if table == "runs" and role == "compliance_analyst":
        return query
    if table == "decisions" and role in ("credit_analyst", "compliance_analyst"):
        return query.where(model.owner == eid) if role == "credit_analyst" else query
    if table == "decision_drafts" and role == "credit_analyst":
        return query.where(model.owner == eid)
    if table in ("cases", "case_events") and role == "service_specialist":
        return query.where(model.owner == eid)
    if table == "policies" and role in ("credit_analyst", "compliance_analyst", "auditor"):
        return query
    if table == "audit" and role in ("compliance_analyst", "auditor"):
        return query
    if table == "campaigns" and role == "marketing_analyst":
        return query.where(model.owner == eid)
    deny(store, table)


def redact(store, table, payload):
    if store.user and table == "runs" and store.user.role_key == "compliance_analyst":
        return {k: v for k, v in payload.items() if k not in ("input_snapshot", "policy_snapshot", "input_hash")}
    return payload


def authorize_write(store, table, data, owner, update=False):
    if not store.user or table == "audit":
        return
    features = {"grants": "staff.creditresearch", "runs": "staff.creditresearch", "decisions": "staff.decision",
                "decision_drafts": "staff.decision",
                "cases": "staff.cases", "case_events": "staff.cases", "redemptions": "staff.benefits",
                "catalog": "staff.benefits", "benefit_rules": "staff.benefits"}
    feature = features.get(table)
    if not feature:
        deny(store, table)
    require_feature(store, feature, write=True)
    if table in ("catalog", "benefit_rules"):
        if store.user.role_key != "benefits_admin":
            deny(store, table)
    elif owner != store.user.employee_id:
        deny(store, table)
    if update and store.db.scalar(scoped_query(store, table).where(RECORD_MODELS[table].id == data["id"])) is None:
        deny(store, table)
