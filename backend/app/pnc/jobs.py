"""Background job runner with idempotency keys, bounded retry and a persisted status (table `pnc_jobs`).

`run_job` works in-process (CLI, API background tasks). `app/pnc/celery_app.py` wraps the same function for Celery/Redis;
the Celery path is optional and is only usable with a running Redis broker.
"""
from __future__ import annotations

import json
import time
import traceback
import uuid
from typing import Callable

from sqlalchemy import text

from app.core.db import db_session


class JobFailed(RuntimeError):
    pass


def get_job(idempotency_key: str) -> dict | None:
    with db_session() as s:
        r = s.execute(text("SELECT job_id, job_name, idempotency_key, status, attempts, max_attempts, scheduled_at, started_at, finished_at, error, result "
                           "FROM pnc_jobs WHERE idempotency_key = :k"), {"k": idempotency_key}).mappings().first()
    return None if r is None else {k: (str(v) if k == "job_id" else (v.isoformat() if hasattr(v, "isoformat") else v)) for k, v in dict(r).items()}


def list_jobs(limit: int = 50) -> list[dict]:
    with db_session() as s:
        rows = s.execute(text("SELECT job_id, job_name, idempotency_key, status, attempts, max_attempts, started_at, finished_at, error "
                              "FROM pnc_jobs ORDER BY scheduled_at DESC LIMIT :n"), {"n": limit}).mappings().all()
    return [{k: (str(v) if k == "job_id" else (v.isoformat() if hasattr(v, "isoformat") else v)) for k, v in dict(r).items()} for r in rows]


def run_job(name: str, fn: Callable[[], dict], *, idempotency_key: str | None = None, max_attempts: int = 3, backoff_seconds: float = 1.0,
            force: bool = False) -> dict:
    """Run `fn` as a tracked job.

    * Same idempotency key + a succeeded job -> the stored result is returned and `fn` is NOT called (unless force=True).
    * A failing `fn` is retried up to `max_attempts` with exponential backoff; every attempt updates the row.
    * After the last attempt the job is marked `failed` with the error text and JobFailed is raised.
    """
    key = idempotency_key or f"{name}:{uuid.uuid4().hex}"
    with db_session() as s:
        s.execute(text("INSERT INTO pnc_jobs(job_id, job_name, idempotency_key, status, attempts, max_attempts, scheduled_at) "
                       "VALUES (:i,:n,:k,'queued',0,:m, now()) ON CONFLICT (idempotency_key) DO NOTHING"),
                  {"i": uuid.uuid4(), "n": name, "k": key, "m": max_attempts})
        row = s.execute(text("SELECT job_id, status, result, attempts FROM pnc_jobs WHERE idempotency_key = :k FOR UPDATE"), {"k": key}).mappings().one()
        if row["status"] == "succeeded" and not force:
            return {"job_id": str(row["job_id"]), "status": "succeeded", "deduplicated": True, "result": row["result"]}
        if row["status"] == "running":
            raise JobFailed(f"job {key} is already running")
        s.execute(text("UPDATE pnc_jobs SET status='running', started_at=now(), finished_at=NULL, error=NULL, attempts=0, max_attempts=:m WHERE job_id=:i"),
                  {"i": row["job_id"], "m": max_attempts})
    job_id = row["job_id"]
    for attempt in range(1, max_attempts + 1):
        try:
            result = fn()
            with db_session() as s:
                s.execute(text("UPDATE pnc_jobs SET status='succeeded', attempts=:a, finished_at=now(), result=CAST(:r AS jsonb) WHERE job_id=:i"),
                          {"a": attempt, "r": json.dumps(result, default=str), "i": job_id})
            return {"job_id": str(job_id), "status": "succeeded", "deduplicated": False, "attempts": attempt, "result": result}
        except Exception as exc:   # noqa: BLE001 - recorded and surfaced
            last = f"{exc.__class__.__name__}: {exc}"
            final = attempt == max_attempts
            with db_session() as s:
                s.execute(text("UPDATE pnc_jobs SET status=:st, attempts=:a, error=:e, finished_at=CASE WHEN :f THEN now() END WHERE job_id=:i"),
                          {"st": "failed" if final else "retrying", "a": attempt, "e": (last + "\n" + traceback.format_exc())[:2000], "f": final, "i": job_id})
            if final:
                raise JobFailed(last) from exc
            time.sleep(backoff_seconds * (2 ** (attempt - 1)))
    raise AssertionError("unreachable")
