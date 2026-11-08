"""Behavioral checks for the Learn API. Run: python tests/test_learn_api.py"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["LEARN_PROGRESS_PATH"] = os.path.join(tempfile.mkdtemp(), "progress.json")

from fastapi.testclient import TestClient

from app.finance_math import amortize, payment
from app.main import app
from app.services.explainer import QUESTION_INDEX, match_question

client = TestClient(app)


def test_health_and_two_views():
    health = client.get("/health")
    assert health.status_code == 200
    home = client.get("/learn")
    assert home.status_code == 200
    body = home.json()
    assert [view["id"] for view in body["views"]] == ["lessons", "knowledge_map"]
    assert len(body["topics"]) == 10
    assert body["explanation_sequence"][0:3] == ["one_sentence", "analogy", "worked_example"]
    assert "go_deeper" in body["explanation_sequence"]
    assert "check_my_understanding" in body["explanation_sequence"]
    assert body["lesson_count"] >= 20


def _text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_text(item) for item in value)
    return ""


def test_every_lesson_follows_section6_sequence():
    listing = client.get("/learn/lessons")
    assert listing.status_code == 200
    lessons = listing.json()["lessons"]
    topics = {row["topic_id"] for row in lessons}
    assert len(topics) == 10
    for row in lessons:
        detail = client.get(f"/learn/lessons/{row['id']}")
        assert detail.status_code == 200
        payload = detail.json()
        explanation = payload["explanation"]
        assert explanation["one_sentence"].strip()
        assert explanation["analogy"].strip()
        assert explanation["worked_example"]["label"] == "toy numbers"
        assert explanation["worked_example"]["steps"]
        assert explanation["what_this_means_for_you"].strip()
        assert explanation["safe_next_step"].strip()
        assert explanation["go_deeper"]["expanded"] is False
        assert "detail" not in explanation["go_deeper"]
        check = explanation["check_my_understanding"]
        assert check["control"] == "check_my_understanding"
        assert len(check["questions"]) >= 2
        for question in check["questions"]:
            assert "answer_index" not in question
        assert "quiz" not in payload


def test_acronyms_are_spelled_on_first_use_and_go_deeper_opens():
    apy = client.get("/learn/lessons/bank-apy").json()["explanation"]["one_sentence"]
    cd = client.get("/learn/lessons/cd-ladder").json()["explanation"]["one_sentence"]
    ira = client.get("/learn/lessons/ira-types").json()["explanation"]["one_sentence"]
    assert "annual percentage yield" in apy
    assert "certificate of deposit" in cd
    assert "individual retirement account" in ira
    opened = client.get("/learn/lessons/amort-payment/go-deeper").json()
    assert opened["expanded"] is True
    assert opened["symbols"]
    assert "P means the amount borrowed" in " ".join(opened["symbols"])
    assert opened["detail"].strip()


def test_knowledge_map_locks_until_prereqs_done():
    graph = client.get("/learn/map", params={"user_id": "map-user"}).json()
    by_id = {node["id"]: node for node in graph["nodes"]}
    assert by_id["pf-cashflow"]["status"] == "available"
    assert by_id["pf-budget"]["status"] == "locked"
    locked = client.get("/learn/lessons/pf-budget", params={"user_id": "map-user"})
    assert locked.status_code == 403
    assert any(edge["source"] == "amort-payment" and edge["target"] == "mtg-payment" for edge in graph["edges"])
    node = client.get("/learn/map/mtg-payment", params={"user_id": "map-user"})
    assert node.status_code == 200
    assert "amort-payment" in node.json()["prerequisites"]
    assert "mtg-equity" in node.json()["unlocks"]


def test_quiz_saves_progress_and_recommends_next():
    lesson = client.get("/learn/lessons/pf-cashflow").json()
    questions = lesson["explanation"]["check_my_understanding"]["questions"]
    answers = {"q1": 0, "q2": 1}
    assert {question["id"] for question in questions} == set(answers)
    submitted = client.post(
        "/learn/lessons/pf-cashflow/check-my-understanding",
        json={"user_id": "quiz-user", "answers": answers},
    )
    assert submitted.status_code == 200
    body = submitted.json()
    assert body["control"] == "check_my_understanding"
    assert body["score"] == 1
    assert body["questions"][0]["explanation"]["simple"]
    progress = client.get("/learn/progress/quiz-user").json()
    assert "pf-cashflow" in progress["completed_lessons"]
    assert progress["recommended_lesson_id"] == "pf-budget"
    graph = client.get("/learn/map", params={"user_id": "quiz-user"}).json()
    by_id = {node["id"]: node for node in graph["nodes"]}
    assert by_id["pf-cashflow"]["status"] == "completed"
    assert by_id["pf-budget"]["status"] == "available"


def test_scenario_grade():
    scenario = client.get("/learn/scenarios/sc-refi").json()
    assert "36" in scenario["situation"]
    submitted = client.post(
        "/learn/scenarios/sc-refi/grade",
        json={"user_id": "scenario-user", "answers": {"q1": 0, "q2": 0}},
    )
    assert submitted.status_code == 200
    assert submitted.json()["score"] == 1


def test_tracker_apy_and_all_questions_render():
    token = client.post("/api/v1/auth/dev-login", json={"persona_id": "1000"}).json()["access_token"]
    headers = {"Authorization": "Bearer " + token}
    body = client.post(
        "/learn/agent",
        json={"question": "Explain APY", "tracker_user_id": 1000}, headers=headers,
    ).json()
    assert body["matched"] is True
    assert body["question_id"] == "explain-apy"
    assert "annual percentage yield" in body["explanation"]["one_sentence"].lower()
    for question_id in QUESTION_INDEX:
        result = client.post("/learn/context/explain", json={"question_id": question_id, "tracker_user_id": 1000, "go_deeper": True}, headers=headers)
        assert result.status_code == 200
        explanation = result.json()["explanation"]
        assert explanation["one_sentence"].strip()
        assert explanation["analogy"].strip()
        assert explanation["worked_example"]["steps"]
        assert explanation["what_this_means_for_you"].strip()
        assert explanation["go_deeper"]["expanded"] is True
        assert explanation["go_deeper"]["detail"].strip()


def test_question_router_does_not_invent_a_formula():
    body = client.post("/learn/agent", json={"question": "What is the weather on Mars?"}).json()
    assert body["matched"] is False
    assert body["prompts"]
    assert match_question("What is credit utilization?", None).id == "credit-utilization"


def test_worked_refi_example_matches_formula():
    kept = amortize(12000, 10, 36)
    assert abs(kept.payment - 387.21) < 0.05
    assert abs(kept.total_interest - 1939) < 2
    same = payment(12000, 6, 36)
    longer = payment(12000, 6, 60)
    assert same < kept.payment
    assert longer < same


if __name__ == "__main__":
    import traceback

    failed = 0
    tests = [value for name, value in list(globals().items()) if name.startswith("test_") and callable(value)]
    for fn in tests:
        try:
            fn()
            print("ok", fn.__name__)
        except Exception:
            failed += 1
            traceback.print_exc()
    print(f"{len(tests) - failed} passed, {failed} failed")
    raise SystemExit(failed)
