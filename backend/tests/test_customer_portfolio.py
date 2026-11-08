from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.orm.models import InvestmentProfile, PortfolioAccount, PortfolioHistory
from app.staff.store import Store


def login(client, persona="1000"):
    response = client.post("/api/v1/auth/dev-login", json={"persona_id": persona})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


def test_customer_portfolio_is_owned_and_staff_routes_remain_protected():
    client = TestClient(app)
    assert client.get("/api/v1/pnc/portfolio").status_code == 401
    headers = login(client)
    response = client.get("/api/v1/pnc/portfolio", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["client_id"] == 1000
    assert sum(h["value_cents"] for h in body["holdings"]) == body["value_cents"]
    assert client.get("/staff/portfolio/clients", headers=headers).status_code == 403
    assert client.post("/api/v1/pnc/portfolio/preview", headers=headers, json={"client_id": 1001}).status_code == 422
    other = login(client, "1001")
    assert client.get("/api/v1/pnc/portfolio", headers=other).json()["client_id"] == 1001
    staff = login(client, "E005")
    assert client.get("/api/v1/pnc/portfolio", headers=staff).status_code == 403


def test_profile_and_allocation_previews_recalculate_without_saving():
    client = TestClient(app)
    headers = login(client)
    baseline = client.get("/api/v1/pnc/portfolio", headers=headers).json()
    profile = {key: baseline["profile"][key] for key in (
        "goal", "horizon_months", "tolerance", "liquidity_need_cents", "target_return")}
    profile.update(horizon_months=120, tolerance=1, liquidity_need_cents=0)
    body = {"profile": profile, "investment_cents": 100000,
            "allocations": {"stocks": "0.2", "bonds": "0.7", "foreign": "0.1"}}
    low = client.post("/api/v1/pnc/portfolio/preview", headers=headers, json=body)
    assert low.status_code == 200, low.text
    assert low.json()["preview_only"] is True
    assert low.json()["assessment"]["allocations"] == {"stocks": .2, "bonds": .7, "foreign": .1}
    profile["tolerance"] = 5
    high = client.post("/api/v1/pnc/portfolio/preview", headers=headers, json=body)
    assert high.status_code == 200, high.text
    assert high.json()["assessment"]["risk_budget"] > low.json()["assessment"]["risk_budget"]
    suggestion = high.json()["assessment"]["profile_model"]
    assert suggestion is not None
    assert abs(sum(suggestion["allocations"].values()) - 1) < .000001
    assert suggestion["metrics"]["volatility"] <= high.json()["assessment"]["risk_budget"]
    assert max(suggestion["allocations"].values()) <= .8
    assert suggestion["requires_approval"] is True
    with Store() as store:
        account = store.db.get(PortfolioAccount, 1000)
        assert account.value_cents == baseline["value_cents"]
        assert account.revision == 1
        assert store.db.get(InvestmentProfile, 1000).tolerance == baseline["profile"]["tolerance"]
        history = store.db.scalars(select(PortfolioHistory).where(PortfolioHistory.client_id == 1000)).all()
        assert len(history) == 1
    body["allocations"] = {"stocks": "0.7", "bonds": "0.7", "foreign": "0.1"}
    assert client.post("/api/v1/pnc/portfolio/preview", headers=headers, json=body).status_code == 422
