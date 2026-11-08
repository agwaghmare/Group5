"""Authenticated ElevenLabs speech relay. Credentials stay on the server."""
import os
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.orm.identity import current_identity
from app.orm.models import AuthSession, User
from app.staff.store import now

router = APIRouter(prefix="/api/v1/speech", tags=["Assistant speech"])
VOICES = {"Amelia": "EXAVITQu4vr4xnSDxMaL", "Wilbur": "JBFqnCBsd6RMkjVDRZzb"}
MAX_AUDIO = 5 * 1024 * 1024


class Speak(BaseModel):
    text: str = Field(min_length=1, max_length=6000)
    assistant: Literal["Amelia", "Wilbur"] = "Amelia"


def credential():
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key or key.startswith("YOUR_"):
        raise HTTPException(503, "ElevenLabs voice is not configured. You can use a browser voice.")
    return key


def recheck(store):
    store.db.expire_all()
    user = store.db.get(User, store.user.id)
    auth = store.db.get(AuthSession, store.auth_token_digest)
    if not user or not user.active or not auth or auth.payload["expires_at"] <= now():
        raise HTTPException(401, "Your session expired. Sign in again to use voice.")


def request_speech(path, **kwargs):
    try:
        with httpx.Client(timeout=httpx.Timeout(40, connect=5), follow_redirects=False) as client:
            response = client.post("https://api.elevenlabs.io/v1/" + path,
                                   headers={"xi-api-key": credential()}, **kwargs)
        if response.status_code in (401, 403):
            raise HTTPException(503, "ElevenLabs rejected the voice credential or permissions.")
        if response.status_code == 429:
            raise HTTPException(503, "ElevenLabs voice quota or rate limit reached. Try a browser voice.")
        if not response.is_success:
            raise HTTPException(502, "ElevenLabs could not complete the voice request. Try again.")
        return response
    except httpx.TimeoutException:
        raise HTTPException(504, "Voice generation timed out. Try again.") from None
    except httpx.HTTPError:
        raise HTTPException(502, "The voice service could not be reached.") from None


@router.get("/config")
def config(store=Depends(current_identity)):
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    return {"enabled": bool(key) and not key.startswith("YOUR_"), "provider": "elevenlabs"}


@router.post("/synthesize")
def synthesize(body: Speak, store=Depends(current_identity)):
    store.db.commit()
    response = request_speech("text-to-speech/" + VOICES[body.assistant], params={"output_format": "mp3_44100_128"},
        json={"text": body.text, "model_id": "eleven_multilingual_v2", "voice_settings": {
            "stability": 0.45, "similarity_boost": 0.75, "style": 0.2, "use_speaker_boost": True, "speed": 0.97}})
    recheck(store)
    if not response.headers.get("content-type", "").startswith("audio/") or not response.content:
        raise HTTPException(502, "The voice service did not return playable audio.")
    return Response(response.content, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@router.post("/transcribe")
def transcribe(file: UploadFile, store=Depends(current_identity)):
    content_type = (file.content_type or "").split(";")[0]
    if content_type not in ("audio/webm", "audio/ogg", "audio/mp4", "audio/wav", "audio/mpeg", "video/webm"):
        raise HTTPException(415, "Record a supported audio format.")
    audio = file.file.read(MAX_AUDIO + 1)
    if not audio or len(audio) > MAX_AUDIO:
        raise HTTPException(413, "Voice questions must be nonempty and under five megabytes.")
    store.db.commit()
    response = request_speech("speech-to-text", files={"file": ("question", audio, content_type)},
        data={"model_id": "scribe_v2", "tag_audio_events": "false", "diarize": "false"})
    recheck(store)
    try:
        text = response.json()["text"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise HTTPException(502, "No speech was recognized. Try again or type your question.") from None
    if len(text) > 2000:
        raise HTTPException(422, "Please ask a shorter voice question.")
    return {"text": text.strip()}
