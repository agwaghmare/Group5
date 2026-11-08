"""Lessons view, knowledge-map view, quizzes, scenarios, and decision explanations."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.orm.access import customer_scope
from app.orm.identity import current_identity
from app.staff.store import Store

from app.content.curriculum import LESSON_INDEX, LESSONS, SCENARIO_INDEX, SCENARIOS, TOPICS, knowledge_map
from app.examples import render_example
from app.schemas import AnswerSubmission, ExplainRequest, ProgressUpdate
from app.services.context import load_context
from app.services.explainer import explain, prompts_for
from app.services.section6 import present_explanation
from app.services.progress import (
    complete_lesson,
    get_progress,
    record_quiz,
    record_scenario,
    record_view,
    update_progress,
)

router = APIRouter(prefix="/learn", tags=["learn"])


def _public_quiz(item: dict) -> dict:
    return {"id": item["id"], "prompt": item["prompt"], "choices": item["choices"]}


def _lesson_status(lesson: dict, progress: dict | None) -> str:
    if not progress:
        return "available"
    done = set(progress.get("completed_lessons", []))
    if lesson["id"] in done:
        return "completed"
    prereqs_met = all(item in done for item in lesson["prerequisites"])
    return "available" if prereqs_met else "locked"


def _public_lesson(lesson: dict, progress: dict | None, go_deeper: bool = False) -> dict:
    scores = progress.get("quiz_results", {}) if progress else {}
    example = render_example(lesson["example"])
    questions = [_public_quiz(item) for item in lesson["quiz"]]
    return {
        "id": lesson["id"],
        "topic_id": lesson["topic_id"],
        "title": lesson["title"],
        "minutes": lesson["minutes"],
        "summary": lesson["summary"],
        "prerequisites": lesson["prerequisites"],
        "status": _lesson_status(lesson, progress),
        "check_my_understanding_result": scores.get(lesson["id"]),
        "explanation": present_explanation(
            lesson["id"],
            lesson["explanation"],
            example=example,
            number_source="toy",
            go_deeper=go_deeper,
            go_deeper_path=f"/learn/lessons/{lesson['id']}/go-deeper",
            check_my_understanding={
                "prompt": "Check my understanding",
                "submit_path": f"/learn/lessons/{lesson['id']}/check-my-understanding",
                "questions": questions,
            },
        ),
    }


def _grade(items: list[dict], answers: dict[str, int]) -> dict:
    graded = []
    correct = 0
    for item in items:
        chosen = answers.get(item["id"])
        is_correct = chosen == item["answer_index"]
        correct += int(is_correct)
        graded.append(
            {
                "id": item["id"],
                "chosen": chosen,
                "answer_index": item["answer_index"],
                "correct": is_correct,
                "explanation": item["explanation"],
            }
        )
    return {"correct": correct, "total": len(items), "score": round(correct / len(items), 4) if items else 0, "questions": graded}


@router.get("")
def learn_home() -> dict:
    return {
        "views": [
            {"id": "lessons", "title": "Lessons", "path": "/learn/lessons"},
            {"id": "knowledge_map", "title": "Knowledge Map", "path": "/learn/map"},
        ],
        "topics": TOPICS,
        "explanation_sequence": [
            "one_sentence",
            "analogy",
            "worked_example",
            "what_this_means_for_you",
            "safe_next_step",
            "go_deeper",
            "check_my_understanding",
        ],
        "lesson_count": len(LESSONS),
        "scenario_count": len(SCENARIOS),
    }


@router.get("/topics")
def topics() -> dict:
    counts: dict[str, int] = {}
    for lesson in LESSONS:
        counts[lesson["topic_id"]] = counts.get(lesson["topic_id"], 0) + 1
    return {"topics": [{**topic, "lesson_count": counts.get(topic["id"], 0)} for topic in TOPICS]}


@router.get("/lessons")
def lessons(topic_id: str | None = None, user_id: str | None = None) -> dict:
    progress = get_progress(user_id) if user_id else None
    rows = LESSONS if not topic_id else [lesson for lesson in LESSONS if lesson["topic_id"] == topic_id]
    if topic_id and not rows:
        raise HTTPException(status_code=404, detail="Unknown topic")
    return {
        "view": "lessons",
        "lessons": [
            {
                "id": lesson["id"],
                "topic_id": lesson["topic_id"],
                "title": lesson["title"],
                "minutes": lesson["minutes"],
                "summary": lesson["summary"],
                "prerequisites": lesson["prerequisites"],
                "status": _lesson_status(lesson, progress),
            }
            for lesson in rows
        ],
    }


def _reject_if_locked(lesson: dict, progress: dict | None) -> None:
    if _lesson_status(lesson, progress) == "locked":
        raise HTTPException(
            status_code=403,
            detail="This lesson is locked until its prerequisites are complete.",
        )


@router.get("/lessons/{lesson_id}")
def lesson_detail(lesson_id: str, user_id: str | None = None, go_deeper: bool = False) -> dict:
    lesson = LESSON_INDEX.get(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Unknown lesson")
    progress = get_progress(user_id) if user_id else None
    _reject_if_locked(lesson, progress)
    payload = _public_lesson(lesson, progress, go_deeper=go_deeper)
    payload["view"] = "lessons"
    return payload


@router.get("/lessons/{lesson_id}/go-deeper")
def lesson_go_deeper(lesson_id: str, user_id: str | None = None) -> dict:
    lesson = LESSON_INDEX.get(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Unknown lesson")
    progress = get_progress(user_id) if user_id else None
    _reject_if_locked(lesson, progress)
    payload = _public_lesson(lesson, progress, go_deeper=True)
    payload["view"] = "lessons"
    return payload["explanation"]["go_deeper"]


@router.post("/lessons/{lesson_id}/check-my-understanding")
@router.post("/lessons/{lesson_id}/quiz")
def submit_check(lesson_id: str, body: AnswerSubmission) -> dict:
    lesson = LESSON_INDEX.get(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Unknown lesson")
    progress = get_progress(body.user_id)
    _reject_if_locked(lesson, progress)
    graded = _grade(lesson["quiz"], body.answers)
    progress = record_quiz(body.user_id, lesson_id, graded["correct"], graded["total"])
    return {"control": "check_my_understanding", "lesson_id": lesson_id, **graded, "progress": progress}


@router.get("/map")
def map_view(user_id: str | None = None) -> dict:
    progress = get_progress(user_id) if user_id else None
    graph = knowledge_map()
    done = set(progress.get("completed_lessons", [])) if progress else set()
    nodes = []
    for node in graph["nodes"]:
        lesson = LESSON_INDEX[node["id"]]
        prereqs_met = all(item in done for item in lesson["prerequisites"]) if progress else True
        status = "completed" if node["id"] in done else ("available" if prereqs_met else "locked")
        nodes.append({**node, "status": status, "summary": lesson["summary"]})
    return {"view": "knowledge_map", "topics": graph["topics"], "nodes": nodes, "edges": graph["edges"]}


@router.get("/map/{node_id}")
def map_node(node_id: str, user_id: str | None = None) -> dict:
    if node_id not in LESSON_INDEX:
        raise HTTPException(status_code=404, detail="Unknown map node")
    graph = map_view(user_id)
    node = next(item for item in graph["nodes"] if item["id"] == node_id)
    unlocks = [edge["target"] for edge in graph["edges"] if edge["source"] == node_id]
    return {
        "view": "knowledge_map",
        "node": node,
        "prerequisites": node["prerequisites"],
        "unlocks": unlocks,
        "lesson_path": f"/learn/lessons/{node_id}",
    }


@router.get("/scenarios")
def scenarios(topic_id: str | None = None) -> dict:
    rows = SCENARIOS if not topic_id else [item for item in SCENARIOS if item["topic_id"] == topic_id]
    return {
        "scenarios": [
            {
                "id": item["id"],
                "topic_id": item["topic_id"],
                "title": item["title"],
                "lesson_id": item["lesson_id"],
                "situation": item["situation"],
            }
            for item in rows
        ]
    }


@router.get("/scenarios/{scenario_id}")
def scenario_detail(scenario_id: str) -> dict:
    item = SCENARIO_INDEX.get(scenario_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Unknown scenario")
    return {
        "id": item["id"],
        "topic_id": item["topic_id"],
        "title": item["title"],
        "lesson_id": item["lesson_id"],
        "situation": item["situation"],
        "check_my_understanding": {
            "control": "check_my_understanding",
            "prompt": "Check my understanding",
            "questions": [_public_quiz(question) for question in item["questions"]],
        },
    }


@router.post("/scenarios/{scenario_id}/grade")
def grade_scenario(scenario_id: str, body: AnswerSubmission) -> dict:
    item = SCENARIO_INDEX.get(scenario_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Unknown scenario")
    graded = _grade(item["questions"], body.answers)
    progress = record_scenario(body.user_id, scenario_id, graded["correct"], graded["total"])
    return {"scenario_id": scenario_id, **graded, "progress": progress}


@router.get("/progress/{user_id}")
def read_progress(user_id: str) -> dict:
    return get_progress(user_id)


@router.put("/progress/{user_id}")
def write_progress(user_id: str, body: ProgressUpdate) -> dict:
    try:
        return update_progress(user_id, body.preferred_level, body.current_lesson_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown lesson") from None


@router.post("/progress/{user_id}/lessons/{lesson_id}/complete")
def mark_complete(user_id: str, lesson_id: str) -> dict:
    try:
        return complete_lesson(user_id, lesson_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown lesson") from None


@router.get("/context/prompts")
def context_prompts(customer_id: str | None = None, tracker_user_id: int | None = None, authorization: str | None = Header(default=None)) -> dict:
    ctx = authorized_context(customer_id, tracker_user_id, authorization)
    return {
        "customer_id": customer_id,
        "tracker_user_id": tracker_user_id,
        "notes": ctx.notes,
        "prompts": prompts_for(ctx),
    }


@router.post("/context/explain")
def context_explain(body: ExplainRequest, authorization: str | None = Header(default=None)) -> dict:
    if not body.question and not body.question_id:
        raise HTTPException(status_code=400, detail="Send a question or a question_id")
    result = explain(
        body.question_id,
        body.question,
        body.customer_id,
        body.tracker_user_id,
        go_deeper=body.go_deeper,
        context=authorized_context(body.customer_id, body.tracker_user_id, authorization),
    )
    if not result.get("matched") and body.lesson_id:
        lesson = LESSON_INDEX.get(body.lesson_id)
        if lesson is None:
            raise HTTPException(status_code=404, detail="Unknown lesson")
        progress = get_progress(body.user_id) if body.user_id else None
        _reject_if_locked(lesson, progress)
        example = render_example(lesson["example"])
        result = {
            "matched": True,
            "lesson_id": lesson["id"],
            "lesson_title": lesson["title"],
            "label": body.question or lesson["title"],
            "explanation": present_explanation(
                lesson["id"],
                lesson["explanation"],
                example=example,
                number_source="toy",
                go_deeper=body.go_deeper,
                go_deeper_path=f"/learn/lessons/{lesson['id']}/go-deeper",
            ),
            "notes": ["Answered from this lesson."],
            "prompts": result.get("prompts", []),
        }
    if body.user_id and result.get("matched") and result.get("question_id"):
        record_view(body.user_id, result["question_id"])
    return result


@router.post("/agent")
def learning_agent(body: ExplainRequest, authorization: str | None = Header(default=None)) -> dict:
    """Learning agent: route a question through the Section 6 explanation sequence."""
    return context_explain(body, authorization)


@router.post("/wilbur")
def wilbur_explain(body: ExplainRequest, authorization: str | None = Header(default=None)) -> dict:
    """Wilbur explains the authorized curriculum and code-computed examples."""
    from app.agents.bessie import AgentError, explain as agent_explain

    with Store() as store:
        current_identity(authorization, store)
        user_id, role = store.user.id, store.user.role_key
        grants = store.user.role.features or []
        if "learn.*" not in grants and "learn.explain" not in grants:
            raise HTTPException(403, "Learning explanations are not available for your role")
    # This path retains the same ownership checks and deterministic example math.
    result = context_explain(body, authorization)
    explanation = result["explanation"]
    evidence = {
        "lesson": result.get("lesson_title"),
        "curriculum": {key: explanation[key] for key in (
            "one_sentence", "analogy", "worked_example", "what_this_means_for_you", "safe_next_step")},
        "recorded_numbers": result.get("your_numbers", {}).get("tracker", {}),
    }
    try:
        reply = agent_explain(body.question or result.get("label") or "Explain this lesson in plain words.",
                              role, "learn.explain", evidence, agent="wilbur")
    except AgentError as exc:
        raise HTTPException(exc.status, exc.message.replace("Bessie", "Wilbur")) from None
    # Recheck the session after the provider call, before returning personal data.
    with Store() as store:
        current_identity(authorization, store)
        grants = store.user.role.features or []
        if store.user.id != user_id or store.user.role_key != role or not (
            "learn.*" in grants or "learn.explain" in grants
        ):
            raise HTTPException(403, "Your learning permissions changed. Please try again.")
        if body.customer_id is not None or body.tracker_user_id is not None:
            customer_scope(store, body.tracker_user_id if body.tracker_user_id is not None else body.customer_id)
        store.audit("wilbur_explanation", body.lesson_id or result.get("lesson_id") or "learn")
    return {**result, "wilbur": reply}


def authorized_context(customer_id, tracker_user_id, authorization):
    if customer_id is None and tracker_user_id is None:
        return load_context()
    if not authorization:
        raise HTTPException(401, "Sign in to use personal financial context")
    with Store() as store:
        current_identity(authorization, store)
        requested = tracker_user_id if tracker_user_id is not None else customer_id
        customer = customer_scope(store, requested)
        if customer_id is not None and str(customer_id) != str(customer.tracker_id):
            store.audit("learn_context_denied", str(customer_id), "denied")
            raise HTTPException(403, "You may only use your own financial context")
        store.audit("learn_context_read", str(customer.tracker_id))
        return load_context(customer_id, customer.tracker_id, store.db)
