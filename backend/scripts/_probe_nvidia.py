from app.settings import load_env
import os
import httpx

load_env()
key = os.environ.get("NVIDIA_API_KEY", "")
model = os.environ.get("NVIDIA_MODEL", "")
print("model", model, "key", bool(key))
response = httpx.post(
    "https://integrate.api.nvidia.com/v1/chat/completions",
    headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
    json={
        "model": model,
        "temperature": 0,
        "max_tokens": 40,
        "messages": [{"role": "user", "content": 'Reply with exactly {"ok":true} as JSON.'}],
        "response_format": {"type": "json_object"},
    },
    timeout=45,
)
print(response.status_code)
print(response.text[:800])
