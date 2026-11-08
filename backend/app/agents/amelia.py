"""NVIDIA explanations of authorized customer-finance evidence, with server-rendered fact tokens."""
import json
import os
import re
from decimal import Decimal
from pathlib import Path
from time import monotonic

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

PROMPT = Path(__file__).parent / "prompts" / "amelia.md"
ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
FACT = re.compile(r"\{\{(f\d{4,})\}\}")
FEATURES = (
    "fin.profile", "fin.xray", "fin.futureyou", "fin.moneymission", "fin.immune",
    "fin.moneyleaks", "fin.debt", "fin.rewards", "fin.fraud", "fin.coach", "fin.modellab",
)
RATIO_LEAVES = {"credit_utilization", "dti", "debt_to_income", "utilization", "value"}
MONEY_MARKERS = (
    "_balance", "_income", "_value", "_payment", "_cost", "_contribution", "_equity",
    "_limit", "safe_spend", "new_payment", "price", "down_payment", "loan_amount",
    "projected_balance_30d", "monthly_payment", "principal",
)
PERCENT_MARKERS = ("_apy", "_apr", "_pct", "_rate", "credit_utilization", "dti", "debt_to_income")


class AgentError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=4000)
    reasons: list[str] = Field(max_length=6)
    evidence_ids: list[str] = Field(max_length=80)
    limitations: list[str] = Field(max_length=6)


def _leaf(path):
    return path.split(".")[-1].split("[")[0]


def facts_for(evidence):
    facts = {}

    def visit(value, path, ratio=False):
        if isinstance(value, Decimal):
            value = float(value)
        if isinstance(value, dict):
            for key, item in value.items():
                visit(item, f"{path}.{key}" if path else key,
                      key in RATIO_LEAVES or ratio)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                visit(item, f"{path}[{i}]")
        elif value is not None:
            key = f"f{len(facts):04}"
            facts[key] = {"path": path, "value": value}
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                leaf = _leaf(path)
                if path.endswith("_cents"):
                    facts[key]["display"] = f"${value / 100:,.2f}"
                elif any(leaf.endswith(mark) or leaf == mark.lstrip("_") for mark in MONEY_MARKERS):
                    facts[key]["display"] = f"${value:,.2f}"
                elif ratio or leaf in RATIO_LEAVES:
                    facts[key]["display"] = f"{value * 100:g}%"
                elif any(mark in leaf for mark in PERCENT_MARKERS):
                    facts[key]["display"] = f"{value:g}%"
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
                or re.search(r"\b(I (?:have )?(?:approved|declined|sent|purchased|changed|recorded|transferred)|moved money|application is approved)\b", plain, re.I)):
            raise ValueError("Unsupported model claim")
    if not referenced.issubset(facts) or not set(parsed.evidence_ids).issubset(facts):
        raise ValueError("Unknown evidence citation")
    if not referenced.issubset(parsed.evidence_ids) or (facts and not referenced):
        raise ValueError("Missing evidence citation")

    def render(value):
        return FACT.sub(lambda m: str(facts[m.group(1)].get("display", facts[m.group(1)]["value"])), value)
    return {"answer": render(parsed.answer), "reasons": [render(s) for s in parsed.reasons],
            "limitations": [render(s) for s in parsed.limitations],
            "citations": [{"id": key, **facts[key]} for key in sorted(referenced)],
            "validation": {"passed": True, "checks": ["structured_output", "known_citations", "server_rendered_values"]}}


def explain(question, role, feature, evidence):
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not key or key.startswith("YOUR_"):
        raise AgentError(503, "Amelia is not configured. Set NVIDIA_API_KEY on the backend.")
    facts = facts_for(evidence)
    # Same NVIDIA contract as Bessie on neeti_branch: tokenized facts + json_schema.
    model_facts = {
        fact_id: {
            "path": fact["path"],
            "value": "{{" + fact_id + "}}" if (
                isinstance(fact["value"], (int, float)) and not isinstance(fact["value"], bool)
                or re.search(r"\d", str(fact["value"]))
            ) else fact["value"],
        }
        for fact_id, fact in facts.items()
    }
    model = os.environ.get("NVIDIA_MODEL", DEFAULT_MODEL).strip()
    if not re.fullmatch(r"(?:nvidia/)?[A-Za-z0-9][A-Za-z0-9._-]{0,99}", model):
        raise AgentError(503, "NVIDIA_MODEL must be an NVIDIA model ID, not a URL.")
    if not model.startswith("nvidia/"):
        model = "nvidia/" + model
    example_id = next(iter(facts), None)
    format_example = {"answer": "I can explain the selected evidence.", "reasons": [], "evidence_ids": [], "limitations": []}
    if example_id:
        format_example.update(answer="The supplied fact is {{" + example_id + "}}.", evidence_ids=[example_id])
    request = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": PROMPT.read_text() + "\n\nAUTHORIZED_CONTEXT_JSON:\n" + json.dumps({
                    "role": role,
                    "feature": feature,
                    "fact_map": model_facts,
                    "policy": "Synthetic tracker; educational information, not financial advice",
                    "output_schema": Explanation.model_json_schema(),
                    "format_example_only": format_example,
                }),
            },
            {"role": "user", "content": question},
        ],
        "temperature": 0,
        "max_tokens": 2048,
        "stream": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "amelia_explanation",
                "strict": True,
                "schema": Explanation.model_json_schema(),
            },
        },
        "chat_template_kwargs": {"enable_thinking": False},
    }
    try:
        deadline = monotonic() + 20
        for attempt in range(2):
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise httpx.ReadTimeout("Explanation deadline exceeded")
            with httpx.Client(timeout=httpx.Timeout(remaining, connect=min(5, remaining)), follow_redirects=False) as client:
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
            candidate = response.json()["choices"][0]
            if candidate.get("finish_reason") != "stop" or candidate["message"].get("refusal"):
                raise AgentError(502, "NVIDIA did not return a complete answer. No partial answer was returned.")
            try:
                result = validate_explanation(json.loads(candidate["message"]["content"]), facts)
                break
            except (ValueError, TypeError, ValidationError):
                if attempt:
                    raise
                # Correct the format without echoing the invalid draft or its claims.
                request["messages"][0]["content"] += (
                    "\n\nREGENERATION REQUIREMENTS: The previous draft failed validation. "
                    "Return all four JSON fields. Include at least one {{f0000}}-style "
                    "placeholder from the supplied fact_map in answer or reasons, and list "
                    "every referenced ID in evidence_ids. Listing evidence_ids alone is "
                    "insufficient. Do not write literal digits anywhere in answer, reasons "
                    "or limitations, including time-window labels, numbered lists, dates "
                    "or feature names. Say 'recent overdrafts' instead of a numeric day "
                    "window. Do not add dollar signs or percent signs around placeholders. "
                    "Explain only supplied facts and omit conclusions not computed in evidence."
                )
        else:
            raise AgentError(502, "Amelia's response did not pass evidence validation. No unsupported answer was returned.")
    except httpx.TimeoutException as exc:
        raise AgentError(504, "Amelia timed out. Your records were not changed.") from exc
    except httpx.HTTPError as exc:
        raise AgentError(502, "Amelia could not reach NVIDIA.") from exc
    except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
        raise AgentError(502, "Amelia's response did not pass evidence validation. No unsupported answer was returned.") from exc
    return {**result, "provider": "nvidia", "model": model, "status": "evidence_validated",
            "prompt_version": "amelia-v2"}
