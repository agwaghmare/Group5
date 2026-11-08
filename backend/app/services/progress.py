"""File-backed lesson, quiz, and scenario progress."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.content.curriculum import LESSON_INDEX, SCENARIO_INDEX


DEFAULT_PATH = Path(__file__).resolve().parents[2] / "storage" / "progress.json"
_LOCK = threading.Lock()


def _path() -> Path:
    return Path(os.environ.get("LEARN_PROGRESS_PATH", DEFAULT_PATH))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty(user_id: str) -> dict:
    return {
        "user_id": user_id,
        "preferred_level": "learner",
        "current_lesson_id": None,
        "completed_lessons": [],
        "quiz_results": {},
        "scenario_results": {},
        "viewed_questions": [],
        "updated_at": _now(),
    }


def _load() -> dict:
    path = _path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_progress(user_id: str) -> dict:
    with _LOCK:
        data = _load()
        row = data.get(user_id) or _empty(user_id)
    row["recommended_lesson_id"] = recommend(row)
    return row


def recommend(row: dict) -> str | None:
    done = set(row.get("completed_lessons", []))
    for lesson in LESSON_INDEX.values():
        if lesson["id"] in done:
            continue
        if all(prereq in done for prereq in lesson["prerequisites"]):
            return lesson["id"]
    return None


def update_progress(user_id: str, preferred_level: str | None, current_lesson_id: str | None) -> dict:
    with _LOCK:
        data = _load()
        row = data.get(user_id) or _empty(user_id)
        if preferred_level:
            row["preferred_level"] = preferred_level
        if current_lesson_id:
            if current_lesson_id not in LESSON_INDEX:
                raise KeyError(current_lesson_id)
            row["current_lesson_id"] = current_lesson_id
        row["updated_at"] = _now()
        data[user_id] = row
        _save(data)
    row["recommended_lesson_id"] = recommend(row)
    return row


def complete_lesson(user_id: str, lesson_id: str) -> dict:
    if lesson_id not in LESSON_INDEX:
        raise KeyError(lesson_id)
    with _LOCK:
        data = _load()
        row = data.get(user_id) or _empty(user_id)
        if lesson_id not in row["completed_lessons"]:
            row["completed_lessons"].append(lesson_id)
        row["current_lesson_id"] = lesson_id
        row["updated_at"] = _now()
        data[user_id] = row
        _save(data)
    row["recommended_lesson_id"] = recommend(row)
    return row


def record_quiz(user_id: str, lesson_id: str, correct: int, total: int) -> dict:
    with _LOCK:
        data = _load()
        row = data.get(user_id) or _empty(user_id)
        row["quiz_results"][lesson_id] = {
            "correct": correct,
            "total": total,
            "score": round(correct / total, 4) if total else 0,
            "completed_at": _now(),
        }
        if total > 0 and correct / total >= 0.8 and lesson_id not in row["completed_lessons"]:
            row["completed_lessons"].append(lesson_id)
        row["updated_at"] = _now()
        data[user_id] = row
        _save(data)
    row["recommended_lesson_id"] = recommend(row)
    return row


def record_scenario(user_id: str, scenario_id: str, correct: int, total: int) -> dict:
    if scenario_id not in SCENARIO_INDEX:
        raise KeyError(scenario_id)
    with _LOCK:
        data = _load()
        row = data.get(user_id) or _empty(user_id)
        row["scenario_results"][scenario_id] = {
            "correct": correct,
            "total": total,
            "score": round(correct / total, 4) if total else 0,
            "completed_at": _now(),
        }
        row["updated_at"] = _now()
        data[user_id] = row
        _save(data)
    row["recommended_lesson_id"] = recommend(row)
    return row


def record_view(user_id: str, question_id: str) -> None:
    with _LOCK:
        data = _load()
        row = data.get(user_id) or _empty(user_id)
        if question_id not in row["viewed_questions"]:
            row["viewed_questions"].append(question_id)
        row["updated_at"] = _now()
        data[user_id] = row
        _save(data)
