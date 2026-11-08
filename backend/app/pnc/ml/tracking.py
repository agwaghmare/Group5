"""MLflow (local file store) logging + JSON artifact reports. Logging failure never hides a metric: the JSON report is
always written first."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import BACKEND_DIR, get_settings


def artifact_dir() -> Path:
    p = Path(get_settings().artifact_dir)
    p = p if p.is_absolute() else BACKEND_DIR / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def dataset_fingerprint(df) -> str:
    return hashlib.sha256(df.to_csv(index=False).encode()).hexdigest()[:16]


def log_run(experiment: str, run_name: str, params: dict, metrics: dict, report: dict, model_obj=None) -> dict:
    report = {**report, "logged_at": datetime.now(timezone.utc).isoformat(), "params": params}
    path = artifact_dir() / f"{experiment}_{run_name}.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    info = {"report_path": str(path)}
    try:
        import mlflow
        uri = get_settings().mlflow_tracking_uri
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment(experiment)
        with mlflow.start_run(run_name=run_name) as run:
            mlflow.log_params({k: str(v)[:250] for k, v in params.items()})
            mlflow.log_metrics({k: float(v) for k, v in metrics.items() if isinstance(v, (int, float)) and v == v})
            mlflow.log_artifact(str(path))
            info["mlflow_run_id"] = run.info.run_id
    except Exception as exc:  # recorded, not swallowed silently
        info["mlflow_error"] = f"{type(exc).__name__}: {exc}"
    return info
