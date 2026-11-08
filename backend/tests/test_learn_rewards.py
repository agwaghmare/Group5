"""Rewards come from server-graded quizzes, once per authenticated account/lesson."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.content.curriculum import LESSON_INDEX
from app.main import app


@pytest.fixture
def local(monkeypatch, tmp_path):
    monkeypatch.setenv("LEARN_PROGRESS_PATH", str(tmp_path / "progress.json"))
    return TestClient(app)


def login(client, persona="1000"):
    response = client.post("/api/v1/auth/dev-login", json={"persona_id": persona})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


def answers(lesson="pf-cashflow"):
    return {q["id"]: q["answer_index"] for q in LESSON_INDEX[lesson]["quiz"]}


def test_reward_earned_once_and_owned_by_authenticated_account(local):
    headers = login(local)
    assert local.get("/learn/rewards").status_code == 401
    failed = local.post("/learn/lessons/pf-cashflow/quiz", headers=headers,
                        json={"user_id": "spoofed", "answers": {}})
    assert failed.status_code == 200
    assert failed.json()["reward"]["awarded"] == 0
    assert "pf-cashflow" not in failed.json()["progress"]["completed_lessons"]
    assert local.get("/learn/lessons/pf-budget", headers=headers).status_code == 403
    body = {"user_id": "account:U1001", "answers": answers()}
    earned = local.post("/learn/lessons/pf-cashflow/quiz", headers=headers, json=body)
    assert earned.status_code == 200, earned.text
    assert earned.json()["reward"]["awarded"] == 0.1
    assert earned.json()["progress"]["user_id"] == "account:U1000"
    assert local.get("/learn/lessons/pf-budget", headers=headers).status_code == 200
    replay = local.post("/learn/lessons/pf-cashflow/check-my-understanding", headers=headers, json=body)
    assert replay.json()["reward"]["awarded"] == 0
    assert replay.json()["reward"]["already_earned"] is True
    balance = local.get("/learn/rewards", headers=headers).json()
    assert balance["balance"] == 0.1 and len(balance["earned_lessons"]) == 1
    other = login(local, "1001")
    assert local.get("/learn/rewards", headers=other).json()["balance"] == 0
    assert local.get("/learn/progress/account:U1000").status_code == 401
    assert local.get("/learn/progress/account:U1000", headers=other).json()["user_id"] == "account:U1001"


def test_anonymous_quizzes_and_mark_complete_do_not_mint_coins(local):
    headers = login(local)
    response = local.post("/learn/lessons/pf-cashflow/quiz", json={"user_id": "anonymous", "answers": answers()})
    assert response.status_code == 200 and response.json()["reward"] is None
    assert local.post("/learn/progress/anonymous/lessons/pf-cashflow/complete", headers=headers).status_code == 200
    assert local.get("/learn/rewards", headers=headers).json()["balance"] == 0


def test_concurrent_quiz_replays_only_award_once(local):
    headers = login(local)
    def submit(_):
        response = local.post("/learn/lessons/pf-cashflow/quiz", headers=headers,
                              json={"answers": answers(), "user_id": "different-browser"})
        assert response.status_code == 200, response.text
        return response.json()["reward"]["awarded"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        amounts = list(pool.map(submit, range(2)))
    assert sum(amounts) == 0.1
    assert local.get("/learn/rewards", headers=headers).json()["balance"] == 0.1
