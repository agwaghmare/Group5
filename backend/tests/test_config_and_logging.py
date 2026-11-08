"""No database needed."""
from __future__ import annotations

import json
import logging

import pytest

from app.core.config import Settings, validate_production_settings
from app.core.logging import JsonFormatter


def test_prod_rejects_default_secret():
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validate_production_settings(Settings(app_env="prod", database_url="postgresql://x"))


def test_prod_rejects_missing_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        validate_production_settings(Settings(app_env="prod", jwt_secret="x" * 40, database_url=None))


def test_prod_accepts_explicit_safe_config():
    validate_production_settings(Settings(app_env="prod", jwt_secret="x" * 40, database_url="postgresql://x"))


def test_dev_allows_defaults():
    validate_production_settings(Settings(app_env="dev"))


def test_demo_login_disabled_in_prod(monkeypatch):
    import app.core.config as cfg
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(app_env="prod", demo_login_enabled=True))
    assert cfg.demo_login_allowed() is False


def test_json_log_format_includes_extras_and_no_secret_fields():
    rec = logging.LogRecord("t", logging.INFO, "f", 1, "hello", (), None)
    rec.request_id = "abc"
    payload = json.loads(JsonFormatter().format(rec))
    assert payload["msg"] == "hello" and payload["request_id"] == "abc" and payload["level"] == "INFO"
