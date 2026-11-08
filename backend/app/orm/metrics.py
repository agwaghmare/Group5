"""Authorized aggregate queries. No raw research files leave these functions."""
from sqlalchemy import case, func, select

from app.orm.authorization import deny, require_feature
from app.orm.models import CreditDecision, ProtectedProfile, ResearchRun


def research_metrics(store):
    require_feature(store, "staff.portfolio")
    if store.user.role_key != "portfolio_manager":
        deny(store, "research_metrics")
    rows = store.db.execute(select(ResearchRun.outcome, func.count()).group_by(ResearchRun.outcome)).all()
    n, overrides = store.db.execute(select(func.count(CreditDecision.id), func.sum(case((CreditDecision.override.is_(True), 1), else_=0)))).one()
    return {"group_size": sum(row[1] for row in rows), "outcomes": {r[0]: r[1] if r[1] >= 5 else None for r in rows},
            "decision_count": n if n >= 5 else None, "override_rate": (overrides or 0)/n if n >= 5 else None,
            "suppression_threshold": 5, "suppression_notice": "Groups smaller than five are suppressed."}


def fairness_metrics(store):
    require_feature(store, "staff.fairness")
    latest = select(ResearchRun.prospect_id, ResearchRun.outcome,
        func.row_number().over(partition_by=ResearchRun.prospect_id, order_by=ResearchRun.payload["run_at"].as_string().desc()).label("n")).subquery()
    group = ProtectedProfile.payload["group_label"].as_string()
    rows = store.db.execute(select(group, func.count(), func.sum(case((latest.c.outcome == "MEETS_POLICY", 1), else_=0)))
        .join(latest, latest.c.prospect_id == ProtectedProfile.id).where(latest.c.n == 1).group_by(group)).all()
    return {label: {"n": n, "meets_policy_rate": meets/n} for label, n, meets in rows}
