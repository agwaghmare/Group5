"""Jobs (idempotency/retry), data contract + reproducibility, and API behaviour through the real database."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.db import db_session
from app.pnc import jobs

pytestmark = pytest.mark.db


# ---------------------------------------------------------------- jobs
def test_job_idempotency_returns_stored_result_without_rerunning():
    key, calls = f"test.idem:{uuid.uuid4().hex}", []
    first = jobs.run_job("test.idem", lambda: calls.append(1) or {"v": 1}, idempotency_key=key)
    again = jobs.run_job("test.idem", lambda: calls.append(1) or {"v": 2}, idempotency_key=key)
    assert len(calls) == 1 and again["deduplicated"] is True and again["result"] == {"v": 1}
    assert first["job_id"] == again["job_id"]


def test_job_retries_then_succeeds():
    key, state = f"test.retry:{uuid.uuid4().hex}", {"n": 0}

    def flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise RuntimeError("transient")
        return {"attempts_seen": state["n"]}
    r = jobs.run_job("test.retry", flaky, idempotency_key=key, max_attempts=3, backoff_seconds=0.01)
    assert r["status"] == "succeeded" and r["attempts"] == 3
    assert jobs.get_job(key)["status"] == "succeeded"


def test_job_marks_failed_after_max_attempts():
    key = f"test.fail:{uuid.uuid4().hex}"

    def boom():
        raise ValueError("always")
    with pytest.raises(jobs.JobFailed):
        jobs.run_job("test.fail", boom, idempotency_key=key, max_attempts=2, backoff_seconds=0.01)
    j = jobs.get_job(key)
    assert j["status"] == "failed" and j["attempts"] == 2 and "always" in j["error"]


# ---------------------------------------------------------------- data contract
def test_loaded_data_matches_contract():
    with db_session() as s:
        one = lambda q: s.execute(text(q)).scalar_one()  # noqa: E731
        assert one("SELECT count(*) FROM pnc_customers") == 30
        assert one("SELECT count(*) FROM pnc_accounts") == 196
        assert one("SELECT count(DISTINCT account_type) FROM pnc_accounts") == 8
        assert one("SELECT count(*) FROM pnc_monthly_statements") == 4704
        assert one("SELECT count(DISTINCT statement_month) FROM pnc_monthly_statements") == 24
        assert one("SELECT min(statement_month)::text FROM pnc_monthly_statements") == "2024-11-01"
        assert one("SELECT max(statement_month)::text FROM pnc_monthly_statements") == "2026-10-01"
        assert one("SELECT count(*) FROM silver_quarantine") == 0


def test_balances_are_positive_for_assets_and_liabilities():
    with db_session() as s:
        assert s.execute(text("SELECT count(*) FROM pnc_accounts WHERE balance < 0")).scalar_one() == 0
        assert s.execute(text("SELECT count(*) FROM pnc_monthly_statements WHERE closing_balance < 0 OR opening_balance < 0")).scalar_one() == 0


def test_no_merchant_field_anywhere():
    with db_session() as s:
        n = s.execute(text("SELECT count(*) FROM information_schema.columns WHERE table_schema='finpilot' AND column_name ILIKE '%merchant%' "
                           "AND table_name LIKE 'pnc_%'")).scalar_one()
        assert n == 0


def test_paired_internal_transfers_are_balanced():
    with db_session() as s:
        bad = s.execute(text("""
            SELECT count(*) FROM (
              SELECT transfer_id FROM pnc_transactions WHERE flow_class = 'internal_transfer'
               GROUP BY transfer_id
              HAVING transfer_id IS NULL OR count(*) <> 2 OR min(amount) <> max(amount)) x""")).scalar_one()
        assert bad == 0
        assert s.execute(text("SELECT count(*) FROM pnc_transactions WHERE flow_class = 'internal_transfer'")).scalar_one() > 0


def test_internal_transfers_excluded_from_income_and_spending_view():
    with db_session() as s:
        r = s.execute(text("""
            SELECT (SELECT coalesce(sum(income),0) FROM gold_monthly_cashflow) AS inc,
                   (SELECT coalesce(sum(amount),0) FROM pnc_transactions WHERE flow_class = 'income') AS raw_inc""")).one()
        assert abs(float(r.inc) - float(r.raw_inc)) < 0.01


def test_generator_is_reproducible(tmp_path: Path):
    from app.pnc.data.generator import generate
    generate(tmp_path)
    for name in ("profiles.csv", "accounts.csv", "transactions.csv", "monthly_statements.csv"):
        from app.core.config import DEMO_PACKAGE_DIR
        a = hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
        b = hashlib.sha256((DEMO_PACKAGE_DIR / name).read_bytes()).hexdigest()
        assert a == b, f"{name} is not reproducible from the fixed seeds"


def test_pipeline_rejects_bad_rows_into_quarantine_not_silently_repaired():
    import pandas as pd

    from app.pnc.data import pipeline as P
    bad = pd.DataFrame({"account_id": ["A0001", "A0002"], "statement_month": ["2025-01-01", "2025-01-01"],
                        "opening_balance": ["100", "100"], "closing_balance": ["150", "999"], "total_increases": ["50", "50"],
                        "total_decreases": ["0", "0"], "source_type": ["x", "x"]})
    good, rejected = P.validate_frame(bad, P.SCHEMAS["pnc_monthly_statements"])
    assert len(good) == 1 and len(rejected) == 1 and "reconcile" in rejected[0][1]


# ---------------------------------------------------------------- API
def test_dev_login_ignores_client_role(client):
    r = client.post("/api/v1/auth/dev-login", json={"persona_id": "C001", "role": "compliance_analyst"})
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "customer"
    assert r.json()["user"]["tabs"] == ["home", "finance", "learn"]
    assert client.post("/api/v1/auth/dev-login", json={"persona_id": "NOPE"}).status_code == 401


def test_forged_token_is_rejected(client):
    import jwt
    forged = jwt.encode({"sub": "U-C001", "role": "customer", "org": "pnc"}, "wrong-secret", algorithm="HS256")
    assert client.get("/api/v1/pnc/profile", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_token_with_wrong_role_is_rejected(client):
    from app.pnc.api.deps import Principal, issue_token
    # correctly signed, but the database says U-C001 is a customer
    t = issue_token(Principal(sub="U-C001", role="compliance_analyst", customer_id="C001"))
    assert client.get("/api/v1/pnc/profile", headers={"Authorization": f"Bearer {t}"}).status_code == 401


def test_token_for_unknown_customer_is_rejected(client):
    from app.pnc.api.deps import Principal, issue_token
    t = issue_token(Principal(sub="U-C999", role="customer", customer_id="C999"))
    assert client.get("/api/v1/pnc/profile", headers={"Authorization": f"Bearer {t}"}).status_code == 401


def test_token_with_wrong_org_is_rejected(client):
    import jwt

    from app.core.config import get_settings
    s = get_settings()
    t = jwt.encode({"sub": "U-C001", "role": "customer", "org": "toyota", "customer_id": "C001"},
                   s.jwt_secret, algorithm=s.jwt_algorithm)
    assert client.get("/api/v1/pnc/profile", headers={"Authorization": f"Bearer {t}"}).status_code == 401


def test_unauthenticated_requests_are_rejected(client):
    for path in ("/api/v1/pnc/profile", "/api/v1/pnc/accounts", "/api/v1/pnc/financial-xray", "/api/v1/pnc/consents"):
        assert client.get(path).status_code == 401, path


def test_staff_login_returns_staff_tabs_and_cannot_use_customer_api(client):
    r = client.post("/api/v1/auth/dev-login", json={"persona_id": "E101"})
    assert r.status_code == 200
    user = r.json()["user"]
    assert user["role"] == "credit_analyst"
    assert user["tabs"] == ["home", "research", "benefits", "learn"]
    assert user["home_route"] == "/research"
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/v1/pnc/profile", headers=h).status_code == 403


def test_staff_routes_no_longer_exist(client, tokens):
    assert client.get("/api/v1/staff/pnc/prospects", headers=tokens("C001")).status_code == 404


def test_customer_cannot_read_another_customers_account_by_id(client, tokens):
    other_account = client.get("/api/v1/pnc/accounts", headers=tokens("C002")).json()["accounts"][0]["account_id"]
    r = client.get(f"/api/v1/pnc/accounts/{other_account}/history", headers=tokens("C001"))
    assert r.status_code in (403, 404)


def test_customer_endpoints_return_only_own_data(client, tokens):
    ids = {a["account_id"] for a in client.get("/api/v1/pnc/accounts", headers=tokens("C001")).json()["accounts"]}
    other = {a["account_id"] for a in client.get("/api/v1/pnc/accounts", headers=tokens("C002")).json()["accounts"]}
    assert ids and other and not (ids & other)


def test_future_as_of_is_rejected(client, tokens):
    assert client.get("/api/v1/pnc/financial-xray?as_of=2030-01-01", headers=tokens("C001")).status_code == 422


def test_xray_response_has_evidence_and_disclaimer(client, tokens):
    x = client.get("/api/v1/pnc/financial-xray", headers=tokens("C001")).json()
    assert x["indicators"] and "disclaimer" in x["overall"]
    assert all("inputs" in i and "source" in i for i in x["indicators"])


def test_health_endpoints(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/db").status_code == 200
