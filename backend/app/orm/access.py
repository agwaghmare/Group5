"""Central row scope: caller identity is loaded from the session, not request roles."""
from fastapi import HTTPException
from sqlalchemy import select

from app.orm.models import Customer, FinanceSnapshot


def customer_scope(store, requested_id=None):
    if store.user.role_key != "customer":
        store.audit("tracker_access_denied", str(requested_id or "customer"), "denied")
        raise HTTPException(403, "This customer view is not available for your role")
    customer = store.db.scalar(select(Customer).where(Customer.user_id == store.user.id))
    if not customer or (requested_id is not None and str(customer.tracker_id) != str(requested_id)):
        store.audit("tracker_access_denied", str(requested_id), "denied")
        raise HTTPException(403, "You may only access your own financial data")
    return customer


def tracker_query(store, requested_id=None):
    customer = customer_scope(store, requested_id)
    return select(FinanceSnapshot).where(FinanceSnapshot.user_id == customer.tracker_id).order_by(FinanceSnapshot.date)


def snapshot_dict(snapshot):
    return {col.name: getattr(snapshot, col.name) for col in FinanceSnapshot.__table__.columns}
