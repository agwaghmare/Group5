import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.orm.models import AuthSession
from app.routers import speech
from app.staff.store import Store, digest

HTTP_CLIENT = httpx.Client


@pytest.fixture
def local():
    with TestClient(app) as client:
        yield client


def login(client):
    response = client.post("/api/v1/auth/dev-login", json={"persona_id": "1000"})
    return {"Authorization": "Bearer " + response.json()["token"]}


def install(monkeypatch, handler):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "private-test-key")
    monkeypatch.setattr(speech.httpx, "Client", lambda **kw: HTTP_CLIENT(transport=httpx.MockTransport(handler), **kw))


def test_speech_requires_authentication_and_does_not_expose_key(local, monkeypatch):
    headers = login(local)
    install(monkeypatch, lambda req: httpx.Response(200, content=b"mp3 audio", headers={"Content-Type": "audio/mpeg"}))
    assert local.get("/api/v1/speech/config").status_code == 401
    assert local.post("/api/v1/speech/synthesize", json={"text": "Hello"}).status_code == 401
    result = local.get("/api/v1/speech/config", headers=headers)
    assert result.json() == {"enabled": True, "provider": "elevenlabs"}
    assert "private-test-key" not in result.text


def test_natural_voice_is_requested_server_side(local, monkeypatch):
    headers = login(local)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=b"mp3 audio", headers={"Content-Type": "audio/mpeg"})

    install(monkeypatch, handler)
    result = local.post("/api/v1/speech/synthesize", headers=headers, json={"assistant": "Amelia", "text": "Your savings are a cushion."})
    assert result.status_code == 200 and result.content == b"mp3 audio"
    assert result.headers["cache-control"] == "no-store"
    assert calls[0].headers["xi-api-key"] == "private-test-key"
    assert calls[0].url.path.endswith(speech.VOICES["Amelia"])
    assert json.loads(calls[0].content)["voice_settings"]["stability"] == .45
    assert local.post("/api/v1/speech/synthesize", headers=headers, json={"text": "x" * 6001}).status_code == 422


def test_transcription_uses_scribe_and_rejects_unsupported_uploads(local, monkeypatch):
    headers = login(local)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"text": "Give me a quick review of my finances"})

    install(monkeypatch, handler)
    result = local.post("/api/v1/speech/transcribe", headers=headers, files={"file": ("q.webm", b"audio", "audio/webm")})
    assert result.status_code == 200
    assert result.json()["text"] == "Give me a quick review of my finances"
    assert b"scribe_v2" in calls[0].content
    for data, mime, status in [(b"image", "image/png", 415), (b"", "audio/webm", 413), (b"a" * (speech.MAX_AUDIO + 1), "audio/webm", 413)]:
        assert local.post("/api/v1/speech/transcribe", headers=headers, files={"file": ("q", data, mime)}).status_code == status
    assert len(calls) == 1


def test_provider_errors_are_safe_and_revoked_sessions_cannot_receive_audio(local, monkeypatch):
    headers = login(local)
    install(monkeypatch, lambda req: httpx.Response(429, json={"detail": "private-test-key internal error"}))
    result = local.post("/api/v1/speech/synthesize", headers=headers, json={"text": "Hello"})
    assert result.status_code == 503 and "private-test-key" not in result.text

    def revoke(request):
        with Store() as store:
            store.db.delete(store.db.get(AuthSession, digest(headers["Authorization"][7:])))
        return httpx.Response(200, content=b"mp3 audio", headers={"Content-Type": "audio/mpeg"})

    install(monkeypatch, revoke)
    result = local.post("/api/v1/speech/synthesize", headers=headers, json={"text": "Hello"})
    assert result.status_code == 401 and b"mp3 audio" not in result.content
