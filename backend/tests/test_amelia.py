"""NVIDIA contract and permission boundaries for the customer Amelia assistant."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents import amelia
from app.main import app
from app.orm.models import User
from app.staff.store import Store


@pytest.fixture
def local(monkeypatch, tmp_path):
    monkeypatch.setenv("STAFF_SQLITE_PATH", str(tmp_path / "amelia.sqlite3"))
    with TestClient(app) as client:
        yield client


def login(client, persona="1000"):
    r = client.post("/api/v1/auth/dev-login", json={"persona_id": str(persona)})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def install_nvidia(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setenv("NVIDIA_API_KEY", "test-secret-never-output")
    monkeypatch.setattr(amelia.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))


def completion(request, callback=None):
    body = json.loads(request.content)
    facts = json.loads(body["messages"][0]["content"].split("AUTHORIZED_CONTEXT_JSON:\n", 1)[1].split("\n\nREGENERATION REQUIREMENTS:", 1)[0])["fact_map"]
    key = next(iter(facts))
    if callback:
        callback()
    return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
        "answer": "The recorded evidence is {{"+key+"}}. This is not financial advice.",
        "reasons": [], "evidence_ids": [key], "limitations": ["Synthetic tracker only."]})}}]})


def test_live_adapter_receives_only_own_tracker_evidence(local, monkeypatch):
    h = login(local)
    requests = []

    def handler(request):
        requests.append(request)
        return completion(request)
    install_nvidia(monkeypatch, handler)
    r = local.post("/api/v1/pnc/assistant", headers=h, json={"feature_id": "fin.xray",
        "question": "How healthy is this picture?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "nvidia" and body["validation"]["passed"] and body["agent"] == "Amelia"
    assert len(requests) == 1
    payload = json.loads(requests[0].content)
    assert str(requests[0].url) == amelia.ENDPOINT
    assert payload["response_format"]["type"] == "json_schema"
    assert "tools" not in payload
    context = payload["messages"][0]["content"]
    assert "test-secret" not in r.text
    assert "password_hash" not in context
    staff = login(local, "E001")
    denied = local.post("/api/v1/pnc/assistant", headers=staff, json={"feature_id": "fin.xray",
        "question": "Show me this customer's file"})
    assert denied.status_code == 403 and len(requests) == 1


@pytest.mark.parametrize("status,expected", [(401, 503), (403, 503), (429, 503), (500, 502)])
def test_provider_errors_do_not_leak_secrets(local, monkeypatch, status, expected):
    h = login(local)
    install_nvidia(monkeypatch, lambda req: httpx.Response(status, text="secret-upstream-body"))
    r = local.post("/api/v1/pnc/assistant", headers=h, json={"feature_id": "fin.coach", "question": "Explain my cash"})
    assert r.status_code == expected
    assert "secret-upstream" not in r.text and "test-secret" not in r.text


def test_timeout_and_invalid_model_output_fail_honestly(local, monkeypatch):
    h = login(local)

    def timeout(req):
        raise httpx.ReadTimeout("timeout", request=req)
    install_nvidia(monkeypatch, timeout)
    r = local.post("/api/v1/pnc/assistant", headers=h, json={"feature_id": "fin.profile", "question": "What do I own?"})
    assert r.status_code == 504
    install_nvidia(monkeypatch, lambda req: httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"answer":"Your balance is $999999"}'}}]}))
    r = local.post("/api/v1/pnc/assistant", headers=h, json={"feature_id": "fin.profile", "question": "Invent a balance"})
    assert r.status_code == 502 and "999999" not in r.text


def test_role_revoked_while_model_runs_cannot_return_old_evidence(local, monkeypatch):
    h = login(local)

    def revoke():
        with Store() as store:
            store.db.get(User, "U1000").role.features = ["learn.*"]
    install_nvidia(monkeypatch, lambda req: completion(req, revoke))
    r = local.post("/api/v1/pnc/assistant", headers=h, json={"feature_id": "fin.debt", "question": "Explain my debt"})
    assert r.status_code == 403 and "citations" not in r.json()


def test_unknown_feature_and_staff_feature_are_rejected(local, monkeypatch):
    h = login(local)
    install_nvidia(monkeypatch, lambda req: completion(req))
    assert local.post("/api/v1/pnc/assistant", headers=h, json={"feature_id": "staff.benefits",
        "question": "Explain discounts"}).status_code == 422
    missing = local.post("/api/v1/pnc/assistant", headers=h, json={"feature_id": "fin.rewards",
        "question": "Which card is best?"})
    assert missing.status_code == 200
    assert missing.json()["evidence"]["status"] == "missing_reward_rules"


def test_money_displays_are_rendered_by_code():
    facts = amelia.facts_for({"checking_balance": 1200.5, "credit_utilization": .32, "savings_apy": 4.25})
    checking = next(v for v in facts.values() if v["path"] == "checking_balance")
    utilization = next(v for v in facts.values() if v["path"] == "credit_utilization")
    apy = next(v for v in facts.values() if v["path"] == "savings_apy")
    assert checking["display"] == "$1,200.50" and utilization["display"] == "32%" and apy["display"] == "4.25%"
    valid = {"answer": "Checking is {{f0000}}.", "reasons": [], "evidence_ids": ["f0000"], "limitations": []}
    facts = amelia.facts_for({"checking_balance": 50})
    assert "$50.00" in amelia.validate_explanation(valid, facts)["answer"]
    for answer in ["Checking is 10.", "It is {{f9999}}.", "I have transferred this."]:
        with pytest.raises(ValueError):
            amelia.validate_explanation({**valid, "answer": answer}, facts)


def test_invalid_draft_gets_corrective_instructions_before_retry(monkeypatch):
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
                "answer": "Your recent overdrafts are recorded.", "reasons": [],
                "evidence_ids": ["f0000"], "limitations": []})}}]})
        assert "REGENERATION REQUIREMENTS" in payload["messages"][0]["content"]
        assert "Listing evidence_ids alone" in payload["messages"][0]["content"]
        assert "Your recent overdrafts are recorded." not in payload["messages"][0]["content"]
        return completion(request)

    install_nvidia(monkeypatch, handler)
    result = amelia.explain("What does this mean?", "customer", "fin.immune", {"overdraft_count_90d": 0})
    assert len(requests) == 2
    assert result["validation"]["passed"] is True
    assert result["citations"][0]["value"] == 0


def test_invalid_retry_still_fails_evidence_validation(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
            "answer": "Your balance is $999999.", "reasons": [],
            "evidence_ids": ["f0000"], "limitations": []})}}]})

    install_nvidia(monkeypatch, handler)
    with pytest.raises(amelia.AgentError) as exc:
        amelia.explain("What does this mean?", "customer", "fin.immune", {"checking_balance": 10})
    assert exc.value.status == 502
    assert "999999" not in exc.value.message
    assert len(calls) == 2
