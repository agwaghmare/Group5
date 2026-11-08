"""All original tracker columns for the signed-in customer; no Lab Package adapters."""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.orm.access import snapshot_dict, tracker_query
from app.orm.identity import current_identity
from app.orm.models import TRACKER_COLUMNS

router = APIRouter(prefix="/api/v1/pnc", tags=["Personal finance tracker"])


def snapshots(store, customer_id=None):
    rows = list(store.db.scalars(tracker_query(store, customer_id)))
    store.audit("own_finance_read", str(store.user.customer.tracker_id))
    if not rows:
        raise HTTPException(404, "No financial snapshots found")
    return rows


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
    indicators = []
    for key, label, unit, watch, risk, high_good in [
        ("emergency_fund_months", "Emergency fund", "months", 6, 3, True),
        ("credit_utilization", "Credit utilization", "ratio", .30, .60, False),
        ("liquidity_runway_months", "Liquidity runway", "months", 3, 1, True),
    ]:
        value = getattr(row, key)
        number = float(value) if value is not None else None
        status = ("unavailable" if number is None else
                  ("risk" if number < risk else "watch" if number < watch else "ok") if high_good else
                  ("risk" if number > risk else "watch" if number > watch else "ok"))
        indicators.append({"id": key, "label": label, "unit": unit, "raw": number,
                           "status": status, "normalized": None,
                           "explanation": "Observed synthetic tracker value; thresholds are prototype assumptions.",
                           "source": "personal_finance_tracker_dataset.csv", "safe_action": "Review the source value and context."})
    return {"customer_id": str(row.user_id), "as_of": row.date,
            "overall": {"score": None, "band": "unavailable", "indicators_used": len(indicators),
                        "indicators_total": len(indicators), "disclaimer": "No invented composite score. Tracker-derived indicators only."},
            "indicators": indicators}


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
    # Aggregate observations, not fabricated account IDs or transaction histories.
    return {"accounts": [], "status": "aggregate_data_only", "as_of": row.date,
            "balances": {k: getattr(row, k) for k in ("checking_balance", "savings_balance", "total_debt_balance", "mortgage_balance", "portfolio_value")},
            "message": "The tracker contains aggregate balances; individual account records are not present."}
