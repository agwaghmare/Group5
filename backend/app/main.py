"""Group5 Learn API.

Run from the backend directory:

    pip install -r requirements.txt
    python -m uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.learn import router as learn_router

app = FastAPI(
    title="Group5 Learn API",
    version="1.0.0",
    summary="Lessons, a knowledge map, and three-level explanations of the current decision.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(learn_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
