"""Group5 Learn API.

Run from the backend directory:

    python -m pip install -r requirements.txt
    python -m uvicorn app.main:app --reload --port 8010
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from app.settings import load_env

from app.routers.learn import router as learn_router
from app.routers.staff import router as staff_router

app = FastAPI(
    title="FinPilot Learn and Employee API",
    version="1.0.0",
    summary="Lessons, a knowledge map, and three-level explanations of the current decision.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(learn_router)
app.include_router(staff_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
