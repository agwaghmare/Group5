"""Assigned-client isolation, risk math, constraints and approval lifecycle."""
import json

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.agents import bessie
from app.main import app
from app.orm.accounts import provision_employee
from app.orm.models import FinanceSnapshot, MarketObservation, PortfolioAccount, PortfolioAssignment, PortfolioHistory
from app.portfolio import service
from app.staff.store import Store


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def login(c, persona="E005"):
    r = c.post("/api/v1/auth/dev-login", json={"persona_id": persona})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def assign(c, h):
    rows = c.get("/staff/portfolio/unassigned", headers=h)
    assert rows.status_code == 200, rows.text
    cid = rows.json()["clients"][0]["client_id"]
    r = c.post("/staff/portfolio/assignments", headers=h, json={"client_id": cid})
    assert r.status_code == 201, r.text
    return cid


def second_manager(c):
    with Store() as store:
        provision_employee(store, "second-risk@company.test", "Second Manager", "portfolio_manager",
                           "2024-01-01", "a-strong-test-password", "RISK-2")
    return login(c, "RISK-2")


def test_initialization_idempotent_and_no_finances_exposed_before_assignment(client):
    h = login(client)
    first = client.get("/staff/portfolio/unassigned", headers=h)
    assert first.status_code == 200 and first.json()["clients"]
    row = first.json()["clients"][0]
    assert set(row) == {"client_id", "name", "synthetic"}
    assert client.get(f'/staff/portfolio/clients/{row["client_id"]}', headers=h).status_code == 404
    client.get("/staff/portfolio/unassigned", headers=h)
    with Store() as store:
        assert store.db.scalar(select(func.count()).select_from(MarketObservation)) == 183
        assert store.db.scalar(select(func.count()).select_from(PortfolioHistory)) == store.db.scalar(select(func.count()).select_from(PortfolioAccount))
    assert client.get("/staff/portfolio/clients", headers=h).json()["clients"] == []


def test_zero_equity_in_tracker_is_not_replaced_with_a_default(client):
    h = login(client)
    with Store() as store:
        latest = store.db.scalar(select(FinanceSnapshot).where(FinanceSnapshot.user_id == 1000)
                                 .order_by(FinanceSnapshot.date.desc()).limit(1))
        latest.equity_allocation_pct = 0
    cid = assign(client, h)
    assert cid == 1000
    detail = client.get(f"/staff/portfolio/clients/{cid}", headers=h).json()
    assert detail["allocations"] == {"stocks": 0, "bonds": 1, "foreign": 0}


def test_assignment_private_and_cannot_be_taken_by_another_manager(client):
    h = login(client)
    cid = assign(client, h)
    other = second_manager(client)
    assert client.get(f"/staff/portfolio/clients/{cid}", headers=other).status_code == 404
    assert cid not in [r["client_id"] for r in client.get("/staff/portfolio/unassigned", headers=other).json()["clients"]]
    assert client.post("/staff/portfolio/assignments", headers=other, json={"client_id": cid}).status_code == 409
    assert client.post("/staff/portfolio/assignments", headers=h, json={"client_id": cid}).status_code == 201
    detail = client.get(f"/staff/portfolio/clients/{cid}", headers=h).json()
    assert sum(detail["allocations"].values()) == pytest.approx(1)
    assert sum(h["value_cents"] for h in detail["holdings"]) == detail["value_cents"]
    assert len(detail["holdings"]) == 3 and detail["financial_history"]
    assert "Actual buy/sell trades" in detail["behavior"]["note"]


@pytest.mark.parametrize("persona", ["E001", "E003", "E004", "E006", "E007", "1000"])
def test_other_roles_cannot_read_or_assign_individual_portfolios(client, persona):
    h = login(client, persona)
    assert client.get("/staff/portfolio/unassigned", headers=h).status_code == 403
    assert client.post("/staff/portfolio/assignments", headers=h, json={"client_id": 1000}).status_code == 403
    assert client.get("/staff/portfolio/clients/1000", headers=h).status_code == 403


def test_allocations_constrained_in_api_and_database(client):
    h = login(client)
    cid = assign(client, h)
    for weights in [{"stocks": .5, "bonds": .5, "foreign": .5}, {"stocks": -.1, "bonds": .6, "foreign": .5},
                    {"stocks": "NaN", "bonds": .6, "foreign": .4}, {"stocks": .3333333, "bonds": .3333333, "foreign": .3333334}]:
        assert client.post(f"/staff/portfolio/clients/{cid}/proposals", headers=h,
            json={"allocations": weights, "rationale": "A test allocation proposal."}).status_code == 422
    with Store() as store:
        portfolio = store.db.get(PortfolioAccount, cid)
        portfolio.stocks_ppm = 1000000
        portfolio.bonds_ppm = 1000000
        with pytest.raises(IntegrityError):
            store.db.flush()
        store.db.rollback()


def test_risk_math_uses_covariance_and_drawdown_includes_initial_capital():
    returns = np.array([[.10, .01, -.10], [-.10, -.01, .10], [.05, .01, -.05]])
    metrics = service.performance(returns, [.5, 0, .5])
    assert metrics["volatility"] == 0 and metrics["total_return"] == 0
    negative = service.performance(np.array([[-.10, -.10, -.10], [0, 0, 0]]), [1, 0, 0])
    assert negative["max_drawdown"] == pytest.approx(-.10)
    assert sum(service.allocate_cents(1, [333333, 333333, 333334])) == 1
    assert min(service.allocate_cents(1, [333333, 333333, 333334])) >= 0


def suitable_profile(client, h, cid):
    r = client.put(f"/staff/portfolio/clients/{cid}/profile", headers=h, json={
        "goal": "Preserve capital over a long horizon", "horizon_months": 120, "tolerance": 3,
        "liquidity_need_cents": 0, "target_return": .03})
    assert r.status_code == 200, r.text


def proposal(client, h, cid):
    suitable_profile(client, h, cid)
    r = client.post(f"/staff/portfolio/clients/{cid}/proposals", headers=h,
        json={"rationale": "Align this portfolio with the client's risk budget."})
    assert r.status_code == 201, r.text
    return r.json()


def test_assessment_proposal_approval_and_history(client):
    h = login(client)
    cid = assign(client, h)
    r = client.post(f"/staff/portfolio/clients/{cid}/assessments", headers=h, json={})
    assert r.status_code == 201, r.text
    assert r.json()["observations"] == 60 and r.json()["market_source"].startswith("synthetic")
    assert len(r.json()["return_history"]) == 61
    p = proposal(client, h, cid)
    assert sum(p["after"]["allocations"].values()) == pytest.approx(1)
    assert p["after"]["metrics"]["volatility"] <= p["after"]["risk_budget"]
    assert sum(t["delta_cents"] for t in p["trades"]) == 0
    path = f'/staff/portfolio/clients/{cid}/proposals/{p["id"]}/approve'
    assert client.post(path, headers=h, json={"rationale": "Reviewed the comparison carefully", "confirm_simulated": False}).status_code == 422
    approved = client.post(path, headers=h, json={"rationale": "Reviewed the comparison carefully", "confirm_simulated": True})
    assert approved.status_code == 200, approved.text
    after = client.get(f"/staff/portfolio/clients/{cid}", headers=h).json()
    assert after["revision"] == p["base_revision"] + 1
    assert after["allocations"] == p["after"]["allocations"]
    assert after["proposals"][0]["status"] == "approved"
    assert after["assessment"]["metrics"] == p["after"]["metrics"]
    assert len(after["assessment_history"]) == 3
    assert after["assessment_history"][-1]["metrics"] == r.json()["metrics"]
    assert after["history"][0]["event"] == "simulated_rebalance_approved"
    assert after["history"][0]["sent_externally"] is False
    assert client.post(path, headers=h, json={"rationale": "Reviewed the comparison carefully", "confirm_simulated": True}).status_code == 200
    assert len(client.get(f"/staff/portfolio/clients/{cid}", headers=h).json()["history"]) == len(after["history"])


def test_stale_proposals_rejected_and_proposals_do_not_mutate_portfolio(client):
    h = login(client)
    cid = assign(client, h)
    p = proposal(client, h, cid)
    detail = client.get(f"/staff/portfolio/clients/{cid}", headers=h).json()
    assert detail["allocations"] == p["before"]["allocations"]
    suitable_profile(client, h, cid)
    r = client.post(f'/staff/portfolio/clients/{cid}/proposals/{p["id"]}/approve', headers=h,
        json={"rationale": "Reviewed stale comparison carefully", "confirm_simulated": True})
    assert r.status_code == 409


def test_profile_save_reassesses_risk_and_goal_flags_without_changing_holdings(client):
    h = login(client)
    cid = assign(client, h)
    path = f"/staff/portfolio/clients/{cid}"
    profile = {"goal": "Long-term investment goal", "horizon_months": 120, "tolerance": 1,
               "liquidity_need_cents": 0, "target_return": .01}
    first = client.put(path + "/profile", headers=h, json=profile)
    assert first.status_code == 200, first.text
    before = client.get(path, headers=h).json()
    assert before["assessment"]["risk_budget"] == .06
    second = client.put(path + "/profile", headers=h, json={**profile, "tolerance": 5, "target_return": .30})
    assert second.status_code == 200 and second.json()["saved"] is True
    after = client.get(path, headers=h).json()
    assert after["revision"] == before["revision"] + 1
    assert after["assessment"]["risk_budget"] > before["assessment"]["risk_budget"]
    assert after["assessment"]["stated_tolerance"] == 5
    assert "modeled_return_below_goal" in after["assessment"]["flags"]
    assert after["assessment"]["metrics"] == before["assessment"]["metrics"]
    assert after["holdings"] == before["holdings"]
    assert len(after["assessment_history"]) == 2


def test_profile_save_rolls_back_when_assessment_cannot_be_recalculated(client):
    h = login(client)
    cid = assign(client, h)
    path = f"/staff/portfolio/clients/{cid}"
    before = client.get(path, headers=h).json()
    with Store() as store:
        store.execute("DELETE FROM portfolio_market_history")
    r = client.put(path + "/profile", headers=h, json={"goal": "A profile change that must roll back",
        "horizon_months": 120, "tolerance": 5, "liquidity_need_cents": 0, "target_return": .20})
    assert r.status_code == 409
    after = client.get(path, headers=h).json()
    assert after["profile"] == before["profile"]
    assert after["revision"] == before["revision"]
    assert len(after["history"]) == len(before["history"])


def test_horizon_changes_profile_preview_and_curve_without_changing_current_portfolio(client):
    h = login(client)
    cid = assign(client, h)
    path = f"/staff/portfolio/clients/{cid}/profile"
    body = {"goal": "Long-term investment goal", "horizon_months": 12, "tolerance": 5,
            "liquidity_need_cents": 0, "target_return": .30}
    short = client.put(path, headers=h, json=body).json()["assessment"]
    long = client.put(path, headers=h, json={**body, "horizon_months": 120}).json()["assessment"]
    assert short["risk_budget"] == .06
    assert long["risk_budget"] > short["risk_budget"]
    assert short["binding_limits"] == ["investment_horizon"]
    assert short["metrics"] == long["metrics"]
    assert short["profile_model"]["allocations"] != long["profile_model"]["allocations"]
    assert short["profile_model"]["metrics"] != long["profile_model"]["metrics"]
    assert [r["profile_model_index"] for r in short["return_history"]] != [r["profile_model_index"] for r in long["return_history"]]
    assert [r["portfolio_index"] for r in short["return_history"]] == [r["portfolio_index"] for r in long["return_history"]]
    proposed = client.post(f"/staff/portfolio/clients/{cid}/proposals", headers=h, json={"rationale": "Review this profile-aligned allocation."}).json()
    assert proposed["after"]["allocations"] == long["profile_model"]["allocations"]


def test_tolerance_cannot_override_short_horizon_and_explains_unchanged_preview(client):
    h = login(client)
    cid = assign(client, h)
    path = f"/staff/portfolio/clients/{cid}/profile"
    body = {"goal": "Short-term investment goal", "horizon_months": 12, "tolerance": 1,
            "liquidity_need_cents": 0, "target_return": .30}
    first = client.put(path, headers=h, json=body).json()["assessment"]
    second = client.put(path, headers=h, json={**body, "horizon_months": 24, "tolerance": 5}).json()["assessment"]
    assert first["risk_budget"] == second["risk_budget"] == .06
    assert second["binding_limits"] == ["investment_horizon"]
    assert second["risk_limits"]["stated_tolerance"] == .20
    assert first["profile_model"] == second["profile_model"]


def test_assessment_history_is_immutable(client):
    h = login(client)
    cid = assign(client, h)
    client.post(f"/staff/portfolio/clients/{cid}/assessments", headers=h, json={})
    with Store() as store:
        with pytest.raises(IntegrityError):
            store.execute("DELETE FROM portfolio_assessments")
        store.db.rollback()


def test_bessie_gets_assigned_client_evidence_and_denies_cross_manager(client, monkeypatch):
    h = login(client)
    cid = assign(client, h)
    calls = []
    original = httpx.Client

    def handler(request):
        body = json.loads(request.content)
        context = json.loads(body["messages"][0]["content"].split("AUTHORIZED_CONTEXT_JSON:\n")[1])
        calls.append(context)
        assert any(f["path"] == "risk_capacity" for f in context["fact_map"].values())
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
            "answer": "Review this client's risk budget and modeled exposure.", "reasons": [], "evidence_ids": [], "limitations": []})}}]})

    monkeypatch.setenv("NVIDIA_API_KEY", "synthetic-test-key")
    monkeypatch.setattr(bessie.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    body = {"feature_id": "staff.portfolio", "resource_id": str(cid), "question": "Explain this client's portfolio risk"}
    assert client.post("/staff/assistant", headers=h, json=body).status_code == 200
    assert client.post("/staff/assistant", headers=second_manager(client), json=body).status_code == 404
    assert len(calls) == 1


def test_assignment_foreign_key_prevents_nonexistent_client(client):
    login(client)
    with Store() as store:
        store.db.add(PortfolioAssignment(client_id=99999999, manager_id="E005", assigned_at="2026-11-08"))
        with pytest.raises(IntegrityError):
            store.db.flush()
        store.db.rollback()


def test_manager_activity_is_role_specific_scoped_and_filterable(client):
    h = login(client)
    me = client.get("/staff/me", headers=h).json()
    assert me["tabs"] == ["home", "portfolio", "benefits", "activity"]
    assert "learn.explain" not in me["features"]
    assert client.post("/staff/assistant", headers=h, json={
        "agent": "wilbur", "feature_id": "learn.explain", "question": "hi"}).status_code == 403
    cid = assign(client, h)
    suitable_profile(client, h, cid)
    other = second_manager(client)
    other_cid = assign(client, other)
    client.post(f"/staff/portfolio/clients/{other_cid}/assessments", headers=other, json={})
    response = client.get("/staff/portfolio/activity", headers=h)
    assert response.status_code == 200, response.text
    events = response.json()["events"]
    assert {e["client_id"] for e in events} == {cid}
    assert {e["action"] for e in events} >= {"portfolio_client_assigned", "portfolio_profile_updated", "portfolio_assessed"}
    assert all(e["fields"] and e["when"] for e in events)
    other_events = client.get("/staff/portfolio/activity", headers=other).json()["events"]
    assert {e["client_id"] for e in other_events} == {other_cid}
    filtered = client.get("/staff/portfolio/activity?action=portfolio_assessed&limit=1", headers=h).json()["events"]
    assert len(filtered) == 1 and filtered[0]["action"] == "portfolio_assessed"
    assert client.get("/staff/portfolio/activity?action=unknown", headers=h).status_code == 422
    assert client.get("/staff/portfolio/activity", headers=login(client, "E001")).status_code == 403


def test_manager_activity_migration_does_not_restore_revoked_permissions(client):
    from app.orm.models import Role
    h = login(client)
    with Store() as store:
        role = store.db.get(Role, "portfolio_manager")
        role.tabs = ["home", "portfolio", "benefits", "learn"]
        role.features = [f for f in role.features if f != "staff.portfolio"] + ["learn.explain"]
    me = client.get("/staff/me", headers=h).json()
    assert "activity" in me["tabs"] and "learn" not in me["tabs"]
    assert "staff.portfolio" not in me["features"] and "learn.explain" not in me["features"]
    assert client.get("/staff/portfolio/activity", headers=h).status_code == 403


def test_portfolio_summary_counts_assigned_clients_and_current_assessments(client):
    h = login(client)
    ids = [assign(client, h) for _ in range(5)]
    before = client.get("/staff/portfolio/summary", headers=h).json()
    assert before["assigned_clients"] == 5 and before["assessed_clients"] == 0
    assert before["needs_assessment"] == 5 and before["mean_volatility"] is None
    for cid in ids[:4]:
        assert client.post(f"/staff/portfolio/clients/{cid}/assessments", headers=h, json={}).status_code == 201
    partial = client.get("/staff/portfolio/summary", headers=h).json()
    assert partial["assessed_clients"] == 4 and partial["mean_volatility"] is None
    last = client.post(f"/staff/portfolio/clients/{ids[-1]}/assessments", headers=h, json={})
    assert last.status_code == 201
    complete = client.get("/staff/portfolio/summary", headers=h).json()
    assert complete["assigned_clients"] == complete["assessed_clients"] == 5
    assert complete["needs_assessment"] == 0 and complete["mean_volatility"] is not None
    assert complete["above_risk_budget"] + complete["within_risk_budget"] == 5
    # Repeated assessments count the client once, not every historical assessment row.
    client.post(f"/staff/portfolio/clients/{ids[-1]}/assessments", headers=h, json={})
    assert client.get("/staff/portfolio/summary", headers=h).json()["assessed_clients"] == 5
    other = second_manager(client)
    assert client.get("/staff/portfolio/summary", headers=other).json()["assigned_clients"] == 0
    assert client.get("/staff/portfolio/summary", headers=login(client, "E004")).status_code == 403


def test_portfolio_citations_render_rates_and_money_with_correct_units():
    facts = bessie.facts_for({"metrics": {"volatility": .12, "annualized_return": .045},
        "allocations": {"stocks": .6}, "risk_limits": {"investment_horizon": .06},
        "financial_context": {"monthly_income": 5000}})
    displays = {f["path"]: f["display"] for f in facts.values()}
    assert displays["metrics.volatility"] == "12%"
    assert displays["metrics.annualized_return"] == "4.5%"
    assert displays["allocations.stocks"] == "60%"
    assert displays["risk_limits.investment_horizon"] == "6%"
    assert displays["financial_context.monthly_income"] == "$5,000.00"


def test_summary_client_counts_are_not_formatted_as_risk_percentages():
    facts = bessie.facts_for({"above_risk_budget": 2, "within_risk_budget": 3, "risk_budget": .06, "mean_volatility": .07})
    by_path = {f["path"]: f for f in facts.values()}
    assert "display" not in by_path["above_risk_budget"]
    assert "display" not in by_path["within_risk_budget"]
    assert by_path["risk_budget"]["display"] == "6%"
    assert by_path["mean_volatility"]["display"] == "7%"


def test_high_risk_mix_can_be_previewed_but_cannot_be_approved(client):
    h = login(client)
    cid = assign(client, h)
    suitable_profile(client, h, cid)
    base = f"/staff/portfolio/clients/{cid}"
    before = client.get(base, headers=h).json()
    r = client.post(f"{base}/proposals", headers=h, json={
        "rationale": "A proposed high concentration test.", "allocations": {"stocks": 1, "bonds": 0, "foreign": 0}})
    assert r.status_code == 201, r.text
    preview = r.json()
    assert preview["after"]["allocations"] == {"stocks": 1, "bonds": 0, "foreign": 0}
    assert preview["approval_allowed"] is False
    assert "concentration" in [v["code"] for v in preview["constraint_violations"]]
    # Approval must enforce current calculations even if stored display metadata is tampered with.
    from app.orm.models import RebalanceProposal
    with Store() as store:
        row = store.db.get(RebalanceProposal, preview["id"])
        row.evidence = {**row.evidence, "approval_allowed": True, "constraint_violations": []}
    denied = client.post(f'{base}/proposals/{preview["id"]}/approve', headers=h, json={
        "rationale": "Trying the preview does not authorize trades.", "confirm_simulated": True})
    assert denied.status_code == 422
    after = client.get(base, headers=h).json()
    assert after["allocations"] == before["allocations"]
    assert after["holdings"] == before["holdings"]
    assert after["revision"] == before["revision"]


def test_custom_proposal_uses_requested_allocations_exactly(client):
    h = login(client)
    cid = assign(client, h)
    suitable_profile(client, h, cid)
    weights = {"stocks": .15, "bonds": .75, "foreign": .10}
    response = client.post(f"/staff/portfolio/clients/{cid}/proposals", headers=h, json={
        "allocations": weights, "rationale": "Preview my custom allocation exactly."})
    assert response.status_code == 201, response.text
    p = response.json()
    assert p["after"]["allocations"] == weights
    assert p["after"]["allocations"] != p["before"]["allocations"]
    assert any(t["delta_cents"] != 0 for t in p["trades"])


def test_two_approved_rebalances_persist_and_fresh_assessment_reads_new_split(client):
    h = login(client)
    cid = assign(client, h)
    suitable_profile(client, h, cid)
    base = f"/staff/portfolio/clients/{cid}"
    splits = [{"stocks": .10, "bonds": .60, "foreign": .30},
              {"stocks": .15, "bonds": .75, "foreign": .10}]
    results = []
    for weights in splits:
        preview = client.post(base + "/proposals", headers=h, json={
            "allocations": weights, "rationale": "Verify a distinct allowed rebalance persists."})
        assert preview.status_code == 201, preview.text
        p = preview.json()
        assert p["approval_allowed"]
        applied = client.post(f'{base}/proposals/{p["id"]}/approve', headers=h, json={
            "rationale": "Approve the exact reviewed allocation.", "confirm_simulated": True})
        assert applied.status_code == 200, applied.text
        results.append(p["after"])
    assert results[0]["metrics"] != results[1]["metrics"]
    # Read through an independent app/session and the actual database, not the approval response.
    with TestClient(app) as restarted:
        rerun = restarted.post(base + "/assessments", headers=h, json={})
        assert rerun.status_code == 201, rerun.text
        saved = restarted.get(base, headers=h).json()
    assert rerun.json()["allocations"] == splits[-1]
    assert rerun.json()["metrics"] == results[-1]["metrics"]
    assert saved["assessment"]["metrics"] == results[-1]["metrics"]
    assert saved["allocations"] == splits[-1]
    assert saved["assessment"]["return_history"] == results[-1]["return_history"]
    with Store() as store:
        account = store.db.get(PortfolioAccount, cid)
        assert service.allocation(account) == splits[-1]
        from app.orm.models import PortfolioHolding
        holdings = store.db.scalars(select(PortfolioHolding).where(PortfolioHolding.client_id == cid)).all()
        assert sum(row.value_cents for row in holdings) == account.value_cents
        assert {row.bucket: row.value_cents for row in holdings} == dict(zip(service.BUCKETS,
            service.allocate_cents(account.value_cents, [150000, 750000, 100000])))


def test_unchanged_proposal_cannot_be_approved(client):
    h = login(client)
    cid = assign(client, h)
    p = proposal(client, h, cid)
    base = f"/staff/portfolio/clients/{cid}"
    approved = client.post(f'{base}/proposals/{p["id"]}/approve', headers=h,
                          json={"rationale": "Review and apply the proposed mix.", "confirm_simulated": True})
    assert approved.status_code == 200
    before = client.get(base, headers=h).json()
    same = client.post(f"{base}/proposals", headers=h, json={
        "allocations": before["allocations"], "rationale": "Check the same allocation for no changes."}).json()
    assert same["no_change"] and all(t["delta_cents"] == 0 for t in same["trades"])
    r = client.post(f'{base}/proposals/{same["id"]}/approve', headers=h,
                   json={"rationale": "Try approving the unchanged mix.", "confirm_simulated": True})
    assert r.status_code == 409
    after = client.get(base, headers=h).json()
    assert after["revision"] == before["revision"] and len(after["history"]) == len(before["history"])


def test_bessie_cannot_claim_to_have_rebalanced_a_portfolio():
    with pytest.raises(ValueError):
        bessie.validate_explanation({"answer": "I have rebalanced your portfolio.",
            "reasons": [], "evidence_ids": [], "limitations": []}, {})
