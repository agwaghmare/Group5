"""Environment-based configuration.

The active ORM uses DATABASE_URL, defaulting to local SQLite.
Cloud discovery is disabled; secrets are never written to logs.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = REPO_ROOT / "data"
DEMO_PACKAGE_DIR = DATA_DIR / "lab_package_demo"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BACKEND_DIR / ".env"), extra="ignore")

    app_env: str = Field(default="dev", description="dev | test | prod")
    database_url: str | None = None
    tiger_service_id: str | None = None  # legacy configuration; never auto-connect
    db_schema: str = "finpilot"
    db_pool_size: int = 5
    db_max_overflow: int = 5

    jwt_secret: str = "dev-only-change-me-dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60
    demo_login_enabled: bool = True  # forced off when app_env == "prod"

    as_of_date: str = "2026-10-31"  # end of the sponsor history window
    engine_version: str = "1.0.0"
    min_group_size: int = 5
    grant_ttl_minutes: int = 60

    mlflow_tracking_uri: str = f"sqlite:///{(BACKEND_DIR / 'mlflow.db').as_posix()}"
    artifact_dir: str = str(BACKEND_DIR / "models")
    redis_url: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


DEFAULT_JWT_SECRET = Settings.model_fields["jwt_secret"].default


def validate_production_settings(settings: Settings | None = None) -> None:
    """Fail fast at startup when APP_ENV=prod is combined with unsafe defaults."""
    s = settings or get_settings()
    if s.app_env != "prod":
        return
    problems = []
    if s.jwt_secret == DEFAULT_JWT_SECRET or len(s.jwt_secret) < 32:
        problems.append("JWT_SECRET must be set to a random value of at least 32 characters")
    if not (s.database_url or os.getenv("DATABASE_URL")):
        problems.append("DATABASE_URL must be set explicitly")
    if problems:
        raise RuntimeError("unsafe production configuration: " + "; ".join(problems))


@lru_cache(maxsize=1)
def get_database_url() -> str:
    """Local SQLAlchemy default; no cloud discovery or Tiger CLI calls."""
    url = get_settings().database_url or os.environ.get("DATABASE_URL")
    if not url:
        return "sqlite:///" + str(BACKEND_DIR / "storage" / "finpilot_local.sqlite3")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////") and url != "sqlite:///:memory:":
        return "sqlite:///" + str(BACKEND_DIR / url[len("sqlite:///"):])
    return url


def demo_login_allowed() -> bool:
    settings = get_settings()
    return settings.demo_login_enabled and settings.app_env != "prod"
