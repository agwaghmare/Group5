"""FinPilot PNC backend (customer + staff APIs) and the existing Learn API.

Run from the backend directory:

    pip install -r requirements.txt
    python -m uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import time
import uuid

import sqlalchemy.exc
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings, validate_production_settings
from app.core.logging import configure_logging
from app.pnc.api.auth_routes import router as auth_router
from app.pnc.api.customer import router as customer_router
from app.routers.learn import router as learn_router

validate_production_settings()
configure_logging()
log = logging.getLogger("finpilot.http")

app = FastAPI(
    title="FinPilot PNC backend",
    version="1.0.0",
    summary="PNC-only financial intelligence backend: customer finance services, isolated per customer by PostgreSQL RLS.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if get_settings().app_env != "prod" else [],
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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/db")
def health_db() -> dict:
    from app.core.db import ping
    try:
        r = ping()
        return {"status": "ok", "database_user": r["user"]}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "unavailable", "error": exc.__class__.__name__})
