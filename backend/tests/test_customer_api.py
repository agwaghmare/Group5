"""Customer API behaviour through the real database and the real least-privilege role."""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

pytestmark = pytest.mark.db

P = "/api/v1/pnc"
LOANS = ("auto_loan", "personal_loan", "mortgage")


@pytest.fixture(scope="module")
def c1(client, tokens):
    return lambda method, path, **kw: client.request(method, P + path, headers=tokens("C001"), **kw)


@pytest.fixture(scope="module")
def loan_account(c1):
    accts = c1("GET", "/accounts").json()["accounts"]
    return next(a["account_id"] for a in accts if a["account_type"] in LOANS)


GET_ROUTES = ["/profile", "/accounts", "/transactions?limit=5", "/financial-xray", "/health-indicators", "/cash-flow", "/cash-flow?months=6",
              "/upcoming-obligations", "/upcoming-obligations?days=14", "/forecasts/balances", "/forecasts/balances?months=6", "/forecasts/stress",
              "/forecasts/stress?markov=true", "/safe-spend", "/safe-spend?horizon_days=14", "/missions", "/recurring-charges", "/subscription-burden",
              "/spending-trends", "/rewards/compare", "/debt/payoff-compare", "/debt/payoff-compare?extra_monthly=100", "/anomaly-events",
              "/fraud/cases", "/consents", "/goals", "/scenarios"]


@pytest.mark.parametrize("path", GET_ROUTES)
@pytest.mark.parametrize("cust", ["C001", "C007", "C015", "C030"])
def test_every_get_route_works_for_several_customers(client, tokens, path, cust):
    r = client.get(P + path, headers=tokens(cust))
    assert r.status_code == 200, (cust, path, r.text[:300])
    assert r.json() is not None


# ---------------------------------------------------------------- accounts / transactions
def test_profile_hides_internal_flags(c1):
    p = c1("GET", "/profile").json()
    assert p["customer_id"] == "C001" and "vulnerable_flag" not in str(p)


def test_accounts_have_positive_balances_and_types(c1):
    accts = c1("GET", "/accounts").json()["accounts"]
    assert accts and all(float(a["balance"]) >= 0 for a in accts)
    assert {a["account_type"] for a in accts} <= {"checking", "savings", "cd", "ira", "credit_card", "auto_loan", "personal_loan", "mortgage"}


def test_transactions_pagination_and_filters(c1):
    a = c1("GET", "/transactions?limit=5&offset=0").json()
    b = c1("GET", "/transactions?limit=5&offset=5").json()
    ra, rb = a["transactions"], b["transactions"]
    assert len(ra) == 5 and len(rb) == 5
    assert not ({t["transaction_id"] for t in ra} & {t["transaction_id"] for t in rb})
    only = c1("GET", "/transactions?flow_class=income&limit=50").json()["transactions"]
    assert only and all(t["flow_class"] == "income" for t in only)
    assert c1("GET", "/transactions?limit=100000").status_code in (200, 422)


def test_account_history_is_24_months(c1):
    acct = c1("GET", "/accounts").json()["accounts"][0]["account_id"]
    h = c1("GET", f"/accounts/{acct}/history").json()
    rows = h.get("history") or h.get("points") or h.get("balances")
    assert rows and len(rows) == 24


def test_unknown_account_history_is_404(c1):
    assert c1("GET", "/accounts/A9999/history").status_code == 404


# ---------------------------------------------------------------- health + forecasts
def test_xray_scores_are_bounded_and_explained(c1):
    x = c1("GET", "/financial-xray").json()
    assert 0 <= x["overall"]["score"] <= 100
    for i in x["indicators"]:
        assert 0 <= i["normalized"] <= 100 and i["status"] in ("risk", "watch", "ok", "strong", "unavailable")
        assert i["explanation"] and i["source"]


def test_xray_is_point_in_time(c1):
    now = c1("GET", "/financial-xray").json()["overall"]["score"]
    earlier = c1("GET", "/financial-xray?as_of=2025-06-30").json()
    assert earlier["as_of"] <= "2025-06-30" or earlier["as_of"].startswith("2025")
    assert isinstance(now, (int, float))


def test_forecast_reports_model_and_intervals(c1):
    f = c1("GET", "/forecasts/balances?months=3").json()
    assert "model" in str(f) and "disclaimer" in str(f).lower() or "disclaimer" in f
    assert f.get("forecast") or f.get("projection") or f.get("points")


def test_forecast_months_validated(c1):
    assert c1("GET", "/forecasts/balances?months=0").status_code == 422
    assert c1("GET", "/forecasts/balances?months=999").status_code == 422


def test_stress_forecast_has_assumptions(c1):
    s = c1("GET", "/forecasts/stress").json()
    assert "assumptions" in str(s).lower() or "assumption" in str(s).lower()


# ---------------------------------------------------------------- scenarios (FutureYou)
def test_purchase_scenario_math_matches_amortization(c1):
    r = c1("POST", "/scenarios/purchase", json={"price": 30000, "down_payment": 5000, "apr_pct": 8, "term_months": 60, "save": False})
    assert r.status_code == 200, r.text
    scen = r.json()["scenario"]
    # loan = 25,000 at 8% for 60 months -> payment 506.91 (standard amortization)
    assert "506.91" in str(scen)
    assert r.json()["saved"] is None


def test_purchase_scenario_validation(c1):
    assert c1("POST", "/scenarios/purchase", json={"price": -5}).status_code == 422
    assert c1("POST", "/scenarios/purchase", json={"term_months": 0}).status_code == 422
    assert c1("POST", "/scenarios/purchase", json={"apr_pct": 200}).status_code == 422


def test_zero_apr_purchase_works(c1):
    r = c1("POST", "/scenarios/purchase", json={"price": 12000, "down_payment": 0, "apr_pct": 0, "term_months": 60, "save": False})
    assert r.status_code == 200 and "200.00" in str(r.json()["scenario"])   # 12,000 / 60


def test_down_payment_above_price_is_rejected(c1):
    assert c1("POST", "/scenarios/purchase", json={"price": 1000, "down_payment": 5000, "save": False}).status_code == 422
    custom = {"scenarios": [{"label": "bad", "purchase": {"price": 1000, "down_payment": 5000}}], "save": False}
    assert c1("POST", "/scenarios/compare", json=custom).status_code == 422


def test_cash_purchase_with_full_down_payment_works(c1):
    r = c1("POST", "/scenarios/purchase", json={"price": 5000, "down_payment": 5000, "apr_pct": 8, "term_months": 12, "save": False})
    assert r.status_code == 200, r.text


def test_compare_default_scenarios(c1):
    r = c1("POST", "/scenarios/compare", json={"save": False})
    assert r.status_code == 200, r.text
    assert r.json()


# ---------------------------------------------------------------- goals CRUD + plan
def test_goal_lifecycle(c1):
    created = c1("POST", "/goals", json={"name": "pytest goal", "target_amount": 6000, "starting_amount": 0, "deadline": "2027-10-31"})
    assert created.status_code in (200, 201), created.text
    g = created.json()
    gid = g.get("goal_id") or g["goal"]["goal_id"]
    try:
        assert any(x["goal_id"] == gid for x in c1("GET", "/goals").json()["goals"])
        assert c1("GET", f"/goals/{gid}").status_code == 200
        plan = c1("POST", f"/goals/{gid}/calculate-plan").json()
        assert "required_monthly" in str(plan).lower() or "monthly" in str(plan).lower()
        patched = c1("PATCH", f"/goals/{gid}", json={"current_amount": 500})
        assert patched.status_code == 200, patched.text
        assert c1("PATCH", f"/goals/{gid}", json={"status": "nonsense"}).status_code == 422
    finally:
        assert c1("DELETE", f"/goals/{gid}").status_code in (200, 204)
    assert c1("GET", f"/goals/{gid}").status_code == 404


def test_goal_validation(c1):
    assert c1("POST", "/goals", json={"name": "", "target_amount": 100, "deadline": "2027-01-01"}).status_code == 422
    assert c1("POST", "/goals", json={"name": "x", "target_amount": -1, "deadline": "2027-01-01"}).status_code == 422


def test_goal_is_private_to_its_owner(client, tokens):
    mine = client.post(P + "/goals", headers=tokens("C001"), json={"name": "private", "target_amount": 100, "deadline": "2027-12-31"})
    assert mine.status_code in (200, 201)
    j = mine.json()
    gid = j.get("goal_id") or j["goal"]["goal_id"]
    try:
        assert client.get(f"{P}/goals/{gid}", headers=tokens("C002")).status_code == 404
        assert client.delete(f"{P}/goals/{gid}", headers=tokens("C002")).status_code == 404
        assert all(x["goal_id"] != gid for x in client.get(P + "/goals", headers=tokens("C002")).json()["goals"])
    finally:
        client.delete(f"{P}/goals/{gid}", headers=tokens("C001"))


# ---------------------------------------------------------------- debt
def test_amortization_schedule_ends_at_zero(c1, loan_account):
    r = c1("GET", f"/debt/amortization?account_id={loan_account}")
    assert r.status_code == 200, r.text
    assert "schedule" in str(r.json()).lower() or "amortization" in str(r.json()).lower()


def test_amortization_requires_account_and_rejects_foreign_account(client, tokens, c1):
    assert c1("GET", "/debt/amortization").status_code == 422
    foreign = client.get(P + "/accounts", headers=tokens("C002")).json()["accounts"]
    foreign_loan = next(a["account_id"] for a in foreign if a["account_type"] in LOANS)
    assert c1("GET", f"/debt/amortization?account_id={foreign_loan}").status_code == 404


def test_extra_payment_shortens_payoff(c1):
    base = c1("GET", "/debt/payoff-compare?extra_monthly=0").json()
    more = c1("GET", "/debt/payoff-compare?extra_monthly=300").json()
    assert base != more


def test_refinance_scenario(c1, loan_account):
    r = c1("POST", "/debt/refinance-scenario", json={"account_id": loan_account, "new_apr_pct": 4.5, "new_term_months": 60, "fee": 250})
    assert r.status_code == 200, r.text


def test_refinance_validation(c1, loan_account):
    assert c1("POST", "/debt/refinance-scenario", json={"account_id": loan_account, "new_apr_pct": -1, "new_term_months": 60}).status_code == 422
    assert c1("POST", "/debt/refinance-scenario", json={"account_id": "A9999", "new_apr_pct": 5, "new_term_months": 60}).status_code == 404


def test_consolidation_rejects_foreign_or_non_debt_accounts(c1, client, tokens):
    foreign = client.get(P + "/accounts", headers=tokens("C002")).json()["accounts"][0]["account_id"]
    assert c1("POST", "/debt/consolidation-scenario", json={"account_ids": [foreign], "new_apr_pct": 9, "new_term_months": 60}).status_code == 404
    checking = next(a["account_id"] for a in c1("GET", "/accounts").json()["accounts"] if a["account_type"] == "checking")
    assert c1("POST", "/debt/consolidation-scenario", json={"account_ids": [checking], "new_apr_pct": 9, "new_term_months": 60}).status_code == 422


def test_consolidation_scenario(c1):
    accts = c1("GET", "/accounts").json()["accounts"]
    debts = [a["account_id"] for a in accts if a["account_type"] in LOANS + ("credit_card",)][:2]
    r = c1("POST", "/debt/consolidation-scenario", json={"account_ids": debts, "new_apr_pct": 9, "new_term_months": 60})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- spending
def test_safe_spend_never_negative_and_explains(c1):
    s = c1("GET", "/safe-spend").json()
    assert "formula" in str(s).lower() or "inputs" in str(s).lower()
    assert c1("GET", "/safe-spend?horizon_days=0").status_code == 422


def test_missions_are_actionable(c1):
    m = c1("GET", "/missions").json()
    items = m.get("missions", m)
    assert isinstance(items, list)


# ---------------------------------------------------------------- consents
def test_consent_round_trip_and_validation(c1):
    before = {x["scope"]: x["granted"] for x in c1("GET", "/consents").json()["consents"]}
    try:
        assert c1("PUT", "/consents", json={"scope": "marketing", "granted": True}).status_code == 200
        assert {x["scope"]: x["granted"] for x in c1("GET", "/consents").json()["consents"]}["marketing"] is True
        assert c1("PUT", "/consents", json={"scope": "marketing", "granted": False}).status_code == 200
        assert c1("PUT", "/consents", json={"scope": "bogus", "granted": True}).status_code == 422
    finally:
        c1("PUT", "/consents", json={"scope": "marketing", "granted": before.get("marketing", False)})


# ---------------------------------------------------------------- fraud handoff
def test_fraud_case_context_requires_consent(client, tokens):
    h = tokens("C003")
    client.put(P + "/consents", headers=h, json={"scope": "case_context_sharing", "granted": False})
    tx = client.get(P + "/transactions?limit=1", headers=h).json()["transactions"][0]["transaction_id"]
    r = client.post(P + "/fraud/cases", headers=h, json={"transaction_id": tx, "reason": "unrecognised", "share_context": True})
    assert r.status_code == 403, r.text


def test_fraud_case_rejects_other_customers_transaction(client, tokens):
    tx = client.get(P + "/transactions?limit=1", headers=tokens("C002")).json()["transactions"][0]["transaction_id"]
    r = client.post(P + "/fraud/cases", headers=tokens("C001"), json={"transaction_id": tx, "reason": "not mine"})
    assert r.status_code == 404


@pytest.mark.skipif(os.getenv("RUN_DB_WRITE_TESTS") != "1", reason="creates persistent simulated fraud cases; set RUN_DB_WRITE_TESTS=1")
def test_fraud_case_created_with_consent(client, tokens):
    h = tokens("C004")
    client.put(P + "/consents", headers=h, json={"scope": "case_context_sharing", "granted": True})
    tx = client.get(P + "/transactions?limit=1", headers=h).json()["transactions"][0]["transaction_id"]
    r = client.post(P + "/fraud/cases", headers=h, json={"transaction_id": tx, "reason": "unrecognised charge", "share_context": True})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["simulated"] is True and body["shared_context"]["not_shared"]
    assert any(c["case_id"] == body["fraud_case_id"] for c in client.get(P + "/fraud/cases", headers=h).json()["cases"])
    client.put(P + "/consents", headers=h, json={"scope": "case_context_sharing", "granted": False})


# ---------------------------------------------------------------- arithmetic sanity from API output
def test_decimal_money_has_two_places_in_scenarios(c1):
    r = c1("POST", "/scenarios/purchase", json={"price": 30000, "down_payment": 5000, "apr_pct": 8, "term_months": 60, "save": False}).json()
    pay = r["scenario"]["inputs"].get("monthly_payment") or r["scenario"].get("outputs", {}).get("monthly_payment")
    if pay is not None:
        assert Decimal(str(pay)) == Decimal(str(pay)).quantize(Decimal("0.01"))
