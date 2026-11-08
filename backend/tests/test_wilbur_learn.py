"""Live Wilbur contract, personal-context authorization and session rechecks."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents import bessie
from app.main import app
from app.orm.models import User
from app.staff.store import Store


@pytest.fixture
def local():
    with TestClient(app) as client:
        yield client


def login(client, persona="1000"):
    response = client.post("/api/v1/auth/dev-login", json={"persona_id": persona})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


def provider(monkeypatch, callback=None):
    calls = []
    original = httpx.Client

    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert "You are Wilbur" in payload["messages"][0]["content"]
        assert payload["response_format"]["type"] == "json_schema"
        if callback:
            callback()
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
            "answer": "Annual percentage yield describes how savings grow with compounding.",
            "reasons": [], "evidence_ids": [], "limitations": ["Synthetic learning example only."]})}}]})

    monkeypatch.setenv("NVIDIA_API_KEY", "test-secret")
    monkeypatch.setattr(bessie.httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    return calls


def test_personal_wilbur_requires_login_and_ownership(local, monkeypatch):
    headers = login(local)
    calls = provider(monkeypatch)
    request = {"question_id": "explain-apy", "tracker_user_id": 1000}
    assert local.post("/learn/wilbur", json=request).status_code == 401
    assert local.get("/learn/context/prompts?tracker_user_id=1000", headers=headers).status_code == 200
    response = local.post("/learn/wilbur", json=request, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["wilbur"]["agent"] == "Wilbur"
    assert body["wilbur"]["validation"]["passed"] is True
    assert body["explanation"]["worked_example"]["label"] == "your numbers"
    assert len(calls) == 1
    request["tracker_user_id"] = 1001
    assert local.post("/learn/wilbur", json=request, headers=headers).status_code == 403
    assert len(calls) == 1
    assert "test-secret" not in response.text


def test_wilbur_handles_a_question_about_an_open_lesson(local, monkeypatch):
    headers = login(local)
    calls = provider(monkeypatch)
    response = local.post("/learn/wilbur", headers=headers, json={
        "question": "Give me a small example", "lesson_id": "pf-cashflow"})
    assert response.status_code == 200, response.text
    assert response.json()["lesson_id"] == "pf-cashflow"
    assert response.json()["wilbur"]["agent"] == "Wilbur"
    assert len(calls) == 1


def test_wilbur_rechecks_permissions_after_provider_call(local, monkeypatch):
    headers = login(local)

    def revoke():
        with Store() as store:
            store.db.get(User, "U1000").role.features = ["fin.*"]

    provider(monkeypatch, revoke)
    response = local.post("/learn/wilbur", headers=headers, json={"question_id": "explain-apy", "tracker_user_id": 1000})
    assert response.status_code == 403
    assert "wilbur" not in response.json()


def test_missing_provider_configuration_names_wilbur(local, monkeypatch):
    headers = login(local)
    monkeypatch.setenv("NVIDIA_API_KEY", "")
    response = local.post("/learn/wilbur", headers=headers, json={"question_id": "explain-apy"})
    assert response.status_code == 503
    assert "Wilbur" in response.json()["detail"]
