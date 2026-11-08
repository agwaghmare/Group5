"""Load backend/.env without overriding shell settings or exposing secrets."""
import os
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def load_env():
    path = BACKEND / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_env()
