"""Portfolio / Risk Manager: assignment, analysis and simulated approval only."""
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import Field, model_validator

from app.portfolio import service
from app.routers.staff import Body, session

router = APIRouter(prefix="/staff/portfolio", tags=["Portfolio risk workspace"])


class AssignmentIn(Body):
    client_id: int = Field(gt=0)


class ProfileIn(Body):
    goal: str = Field(min_length=3, max_length=200)
    horizon_months: int = Field(ge=1, le=600)
    tolerance: int = Field(ge=1, le=5)
    liquidity_need_cents: int = Field(ge=0, le=10**12)
    target_return: Decimal = Field(ge=0, le=Decimal("0.30"), max_digits=8, decimal_places=6)


class Allocations(Body):
    stocks: Decimal = Field(ge=0, le=1, max_digits=7, decimal_places=6)
    bonds: Decimal = Field(ge=0, le=1, max_digits=7, decimal_places=6)
    foreign: Decimal = Field(ge=0, le=1, max_digits=7, decimal_places=6)

    @model_validator(mode="after")
    def adds_to_one(self):
        if self.stocks + self.bonds + self.foreign != Decimal(1):
            raise ValueError("Domestic stocks, domestic bonds and foreign holdings must sum exactly to 1")
        return self


class ProposalIn(Body):
    allocations: Allocations | None = None
    rationale: str = Field(min_length=10, max_length=2000)


class ApprovalIn(Body):
    rationale: str = Field(min_length=10, max_length=2000)
    confirm_simulated: bool

    @model_validator(mode="after")
    def confirmed(self):
        if not self.confirm_simulated:
            raise ValueError("Explicitly confirm this simulated rebalance")
        return self


@router.get("/clients")
def clients(store=Depends(session)):
    rows = service.client_queue(store)
    store.audit("portfolio_client_queue_read")
    return {"clients": rows, "disclaimer": service.DISCLAIMER}


@router.get("/activity")
def activity(action: str = Query(default="", max_length=80), limit: int = Query(default=100, ge=1, le=500), store=Depends(session)):
    return service.activity(store, action=action, limit=limit)


@router.get("/unassigned")
def unassigned(search: str = Query(default="", max_length=100), store=Depends(session)):
    rows = service.client_queue(store, unassigned=True, search=search)
    store.audit("portfolio_unassigned_directory_read")
    return {"clients": rows, "limit": 200}


@router.post("/assignments", status_code=201)
def assign(body: AssignmentIn, store=Depends(session)):
    return service.assign_client(store, body.client_id)


@router.get("/clients/{client_id}")
def client(client_id: int, store=Depends(session)):
    return service.client_detail(store, client_id)


@router.put("/clients/{client_id}/profile")
def profile(client_id: int, body: ProfileIn, store=Depends(session)):
    return service.update_profile(store, client_id, body)


@router.post("/clients/{client_id}/assessments", status_code=201)
def assess(client_id: int, store=Depends(session)):
    return service.run_assessment(store, client_id)


@router.post("/clients/{client_id}/proposals", status_code=201)
def propose(client_id: int, body: ProposalIn, store=Depends(session)):
    weights = body.allocations.model_dump() if body.allocations else None
    return service.propose(store, client_id, weights, body.rationale)


@router.post("/clients/{client_id}/proposals/{proposal_id}/approve")
def approve(client_id: int, proposal_id: str, body: ApprovalIn, store=Depends(session)):
    return service.approve(store, client_id, proposal_id, body.rationale)
