"""Role-specific payloads for a frontend; never returns another role's workspace."""
from fastapi import APIRouter, Depends

from app.orm.identity import current_identity, public_user
from app.routers import staff, tracker

router = APIRouter(prefix="/api/v1", tags=["Role views"])


@router.get("/view")
def role_view(store=Depends(current_identity)):
    role = store.user.role_key
    if role == "customer":
        data = tracker.tracker(None, 100, store)
        workspace = "finance"
    else:
        routes = {"credit_analyst": staff.prospect_queue, "service_specialist": staff.cases,
                  "marketing_analyst": staff.portfolio, "portfolio_manager": staff.portfolio,
                  "compliance_analyst": staff.reviews, "auditor": staff.audit,
                  "benefits_admin": staff.benefit_usage}
        if role == "auditor":
            data = staff.audit(store=store)
        else:
            data = routes[role](store)
        workspace = store.user.role.tabs[1]
    store.audit("role_view_read", workspace)
    return {"user": public_user(store.user), "workspace": workspace,
            "tabs": store.user.role.tabs, "features": store.user.role.features, "data": data,
            "authorization": "server-side row and field scope; SQLite has no database-user RLS"}
