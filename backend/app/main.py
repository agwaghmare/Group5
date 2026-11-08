"""FinPilot PNC backend (customer + staff APIs) and the existing Learn API.

Run from the backend directory:

    python -m pip install -r requirements.txt
    python -m uvicorn app.main:app --reload --port 8010
"""

from __future__ import annotations

import logging
import os
import time
import uuid

import sqlalchemy.exc
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings, validate_production_settings
from app.core.logging import configure_logging
from app.routers.identity import router as auth_router
from app.routers.learn import router as learn_router
from app.routers.staff import router as staff_router
from app.routers.tracker import router as customer_router
from app.routers.views import router as views_router
from app.settings import load_env

load_env()
validate_production_settings()
configure_logging()
log = logging.getLogger("finpilot.http")

app = FastAPI(
    title="FinPilot PNC, Learn and Employee API",
    version="1.0.0",
    summary="SQLAlchemy users, roles and personal finance tracker; scoped customer and employee views.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.environ.get("CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080").split(",") if origin.strip() and (origin.strip() != "*" or get_settings().app_env != "prod")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["x-request-id"] = rid
    log.info("request", extra={"request_id": rid, "method": request.method, "path": request.url.path,
                               "status": response.status_code, "ms": round((time.perf_counter() - start) * 1000, 1)})
    return response


@app.exception_handler(sqlalchemy.exc.DBAPIError)
async def db_error(request: Request, exc: sqlalchemy.exc.DBAPIError):
    code = getattr(exc.orig, "sqlstate", None)
    if code == "42501":   # insufficient_privilege / RLS violation enforced by the database
        return JSONResponse(status_code=403, content={"error": "forbidden_by_database_policy"})
    if code in ("23514", "23502", "22P02", "23503", "23505", "P0001"):
        return JSONResponse(status_code=422, content={"error": "constraint_violation", "sqlstate": code})
    log.exception("database error", extra={"sqlstate": code})
    return JSONResponse(status_code=500, content={"error": "internal_error"})


app.include_router(auth_router)
app.include_router(customer_router)
app.include_router(learn_router)
app.include_router(staff_router)
app.include_router(views_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/db")
def health_db() -> dict:
    from sqlalchemy import func, select

    from app.orm.models import FinanceSnapshot, User
    from app.staff.store import Store
    try:
        with Store() as store:
            return {"status": "ok", "database": "sqlalchemy_sqlite", "users": store.db.scalar(select(func.count()).select_from(User)),
                    "financial_snapshots": store.db.scalar(select(func.count()).select_from(FinanceSnapshot))}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "unavailable", "error": exc.__class__.__name__})
