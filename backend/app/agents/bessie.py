"""NVIDIA explanations of authorized evidence, with server-rendered fact tokens."""
import json
import os
import re
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

PROMPT = Path(__file__).parent / "prompts" / "bessie.md"
PROMPTS = {"bessie": PROMPT, "wilbur": PROMPT.with_name("wilbur.md")}
ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
FACT = re.compile(r"\{\{(f\d{4,})\}\}")


class AgentError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=4000)
    reasons: list[str] = Field(max_length=6)
    evidence_ids: list[str] = Field(max_length=80)
    limitations: list[str] = Field(max_length=6)


def configured():
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    return bool(key) and not key.startswith("YOUR_")


def facts_for(evidence):
    facts = {}

    def visit(value, path, ratio=False):
        if isinstance(value, dict):
            for key, item in value.items():
                visit(item, f"{path}.{key}" if path else key,
                      value.get("rule") in ("utilization", "dti", "income_share") and key in ("value", "meets_threshold", "watch_threshold"))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                visit(item, f"{path}[{i}]")
        elif value is not None:
            key = f"f{len(facts):04}"
            facts[key] = {"path": path, "value": value}
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if path.endswith("_cents"):
                    facts[key]["display"] = f"${value / 100:,.2f}"
                elif path.endswith("_percent") or ratio:
                    facts[key]["display"] = f"{value * 100 if ratio else value:g}%"
                elif path.endswith(("new_payment", "revolving_balance", "requested_amount", "requested_limit")):
                    facts[key]["display"] = f"${value:,.2f}"
    visit(evidence, "")
    return facts


def validate_explanation(data, facts):
    parsed = Explanation.model_validate(data)
    strings = [parsed.answer, *parsed.reasons, *parsed.limitations]
    referenced = set()
    for value in strings:
        ids = set(FACT.findall(value))
        referenced |= ids
        plain = FACT.sub("", value)
        if (re.search(r"\d|[$%]|\{\{|\}\}|https?://|<[^>]+>", plain)
                or re.search(r"\b(I (?:have )?(?:approved|declined|sent|purchased|changed|recorded)|application is approved)\b", plain, re.I)):
            raise ValueError("Unsupported model claim")
    if not referenced.issubset(facts) or not set(parsed.evidence_ids).issubset(facts):
        raise ValueError("Unknown evidence citation")
    if not referenced.issubset(parsed.evidence_ids):
        raise ValueError("Missing evidence citation")

    def render(value):
        return FACT.sub(lambda m: str(facts[m.group(1)].get("display", facts[m.group(1)]["value"])), value)
    return {"answer": render(parsed.answer), "reasons": [render(s) for s in parsed.reasons],
            "limitations": [render(s) for s in parsed.limitations],
            "citations": [{"id": key, **facts[key]} for key in sorted(referenced)],
            "validation": {"passed": True, "checks": ["structured_output", "known_citations", "server_rendered_values"]}}


def explain(question, role, feature, evidence, agent="bessie"):
    if agent not in PROMPTS:
        raise AgentError(400, "Unknown assistant")
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not key or key.startswith("YOUR_"):
        raise AgentError(503, "Bessie is not configured. Set NVIDIA_API_KEY on the backend.")
    facts = facts_for(evidence)
    model = os.environ.get("NVIDIA_MODEL", DEFAULT_MODEL).strip()
    if not re.fullmatch(r"(?:nvidia/)?[A-Za-z0-9][A-Za-z0-9._-]{0,99}", model):
        raise AgentError(503, "NVIDIA_MODEL must be an NVIDIA model ID, not a URL.")
    if not model.startswith("nvidia/"):
        model = "nvidia/" + model
    request = {
        "model": model,
        "messages": [
            {"role": "system", "content": PROMPTS[agent].read_text()},
            {"role": "system", "content": json.dumps({"role": role, "feature": feature, "fact_map": facts,
                 "policy": "Synthetic prototype; human decisions only", "output_schema": Explanation.model_json_schema()})},
            {"role": "user", "content": question}],
        "temperature": 0, "max_tokens": 2048, "stream": False,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    try:
        # Fixed HTTPS host, validated model ID, and key in a header (never the URL).
        with httpx.Client(timeout=httpx.Timeout(20, connect=5), follow_redirects=False) as client:
            response = client.post(ENDPOINT, headers={"Authorization": f"Bearer {key}"}, json=request)
        if response.status_code in (401, 403):
            raise AgentError(503, "NVIDIA rejected the configured credential or model access.")
        if response.status_code == 404:
            raise AgentError(503, "The configured NVIDIA model is unavailable. Check NVIDIA_MODEL and account access.")
        if response.status_code == 429:
            raise AgentError(503, "NVIDIA is rate limited or out of quota. Try again later.")
        if response.status_code == 400:
            raise AgentError(502, "NVIDIA rejected the request. Check the API key and model configuration.")
        if not response.is_success:
            raise AgentError(502, "NVIDIA could not complete this request.")
        payload = response.json()
        candidate = payload["choices"][0]
        if candidate.get("finish_reason") != "stop" or candidate["message"].get("refusal"):
            raise AgentError(502, "NVIDIA did not return a complete answer. No partial answer was returned.")
        content = candidate["message"]["content"]
        result = validate_explanation(json.loads(content), facts)
    except httpx.TimeoutException as exc:
        raise AgentError(504, "Bessie timed out. Your records were not changed.") from exc
    except httpx.HTTPError as exc:
        raise AgentError(502, "Bessie could not reach NVIDIA.") from exc
    except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
        raise AgentError(502, "Bessie's response did not pass evidence validation. No unsupported answer was returned.") from exc
    return {**result, "provider": "nvidia", "model": model, "status": "evidence_validated",
            "agent": "Wilbur" if agent == "wilbur" else "Bessie",
            "prompt_version": "wilbur-v1" if agent == "wilbur" else "bessie-v2"}
