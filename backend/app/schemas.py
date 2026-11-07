"""Request bodies for the Learn API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProgressUpdate(BaseModel):
    preferred_level: str | None = Field(default=None, pattern="^(simple|learner|detailed)$")
    current_lesson_id: str | None = None


class AnswerSubmission(BaseModel):
    answers: dict[str, int]
    user_id: str = "local"


class ExplainRequest(BaseModel):
    question: str | None = None
    question_id: str | None = None
    customer_id: str | None = None
    tracker_user_id: int | None = None
    user_id: str | None = None
    go_deeper: bool = False
