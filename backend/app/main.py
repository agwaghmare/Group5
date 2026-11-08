"""FinPilot backend: Learn, employee, and PNC customer APIs.

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
from app.pnc.api.auth_routes import router as auth_router
from app.pnc.api.customer import router as customer_router
from app.routers.learn import router as learn_router
from app.routers.staff import router as staff_router
from app.settings import load_env

load_env()
validate_production_settings()
configure_logging()
log = logging.getLogger("finpilot.http")

_cors = os.environ.get("CORS_ORIGINS", "").strip()
if _cors:
    _origins = [origin.strip() for origin in _cors.split(",") if origin.strip()]
elif get_settings().app_env != "prod":
    _origins = ["*"]
else:
    _origins = []

app = FastAPI(
    title="FinPilot API",
    version="1.0.0",
    summary="Learn, employee, and PNC customer finance services.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
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
