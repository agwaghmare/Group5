"""Optional Celery wiring (Redis broker). NOT exercised by the test suite: it needs a running Redis.

    celery -A app.pnc.celery_app worker --loglevel=INFO

The tasks call the same `run_job` used by the CLI, so idempotency and retry state live in `pnc_jobs`, not in Celery.
"""
from __future__ import annotations

import os

from celery import Celery

from app.pnc import jobs

celery_app = Celery("finpilot", broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"), backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
celery_app.conf.update(task_acks_late=True, task_serializer="json", result_serializer="json", timezone="UTC")


@celery_app.task(name="pnc.ingest")
def ingest_task(force: bool = False) -> dict:
    from app.pnc.data import pipeline
    return jobs.run_job("data.ingest", lambda: pipeline.ingest(force=force), idempotency_key=f"data.ingest:{pipeline.dataset_version(pipeline.DEMO_PACKAGE_DIR)}", force=force)


@celery_app.task(name="pnc.train_cashflow")
def train_cashflow_task() -> dict:
    from app.pnc.ml import cashflow
    return jobs.run_job("ml.train_cashflow", cashflow.train_and_log)


@celery_app.task(name="pnc.train_anomalies")
def train_anomalies_task() -> dict:
    from app.pnc.ml import anomaly
    return jobs.run_job("ml.train_anomalies", anomaly.train_and_log)
