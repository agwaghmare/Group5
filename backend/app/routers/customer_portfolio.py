"""Own-account investment views and read-only what-ifs; no staff privileges or trades."""
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.orm.access import customer_scope
from app.orm.identity import current_identity
from app.orm.models import InvestmentProfile, PortfolioAccount, PortfolioHolding
from app.portfolio import service
from app.routers.portfolio import Allocations, ProfileIn

router = APIRouter(prefix="/api/v1/pnc/portfolio", tags=["Customer investments"])


class PreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    allocations: Allocations | None = None
    profile: ProfileIn | None = None
    investment_cents: int | None = Field(default=None, ge=0, le=10**12)


def own_account(store):
    customer = customer_scope(store)
    account = store.db.get(PortfolioAccount, customer.tracker_id)
    if account is None:
        service.seed_synthetic(store.db, customer.tracker_id)
        account = store.db.get(PortfolioAccount, customer.tracker_id)
    if account is None:
        raise HTTPException(404, "No funded portfolio is recorded for your account")
    return account


@router.get("")
def overview(store=Depends(current_identity)):
    account = own_account(store)
    holdings = store.db.scalars(select(PortfolioHolding).where(PortfolioHolding.client_id == account.client_id)).all()
    store.audit("customer_portfolio_read", str(account.client_id))
    return {"client_id": account.client_id, "value_cents": account.value_cents, "as_of": account.as_of,
            "allocations": service.allocation(account),
            "profile": service.profile_json(store.db.get(InvestmentProfile, account.client_id)),
            "holdings": [{"bucket": h.bucket, "instrument": h.instrument, "value_cents": h.value_cents} for h in holdings],
            "assessment": service.assessment(store, account), "disclaimer": service.DISCLAIMER}


@router.post("/preview")
def preview(body: PreviewIn, store=Depends(current_identity)):
    account = own_account(store)
    profile = service.profile_json(store.db.get(InvestmentProfile, account.client_id))
    if body.profile is not None:
        profile.update(body.profile.model_dump())
    modeled = SimpleNamespace(**{key: getattr(account, key) for key in (
        "client_id", "value_cents", "revision", "stocks_ppm", "bonds_ppm", "foreign_ppm", "as_of")})
    if body.investment_cents is not None:
        modeled.value_cents = body.investment_cents
    weights = {key: float(value) for key, value in body.allocations.model_dump().items()} if body.allocations else None
    result = service.assessment(store, modeled, weights, profile_override=SimpleNamespace(**profile))
    store.audit("customer_portfolio_preview", str(account.client_id))
    return {"client_id": account.client_id, "assessment": result, "preview_only": True,
            "disclaimer": "Read-only what-if. Your profile and holdings have not been changed. " + service.DISCLAIMER}
