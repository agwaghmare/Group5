"""Public concept lookup. Account records and credentials never enter search queries."""
import re
from urllib.parse import urlencode, urlsplit

import httpx

ENDPOINT = "https://api.duckduckgo.com/"


def search_topic(question):
    text = re.sub(r"https?://\S+|\S+@\S+|\d+(?:[.,]\d+)*", "", question.lower())
    for term in ("sharpe ratio", "sortino ratio", "value at risk", "efficient frontier", "standard deviation",
                 "capital asset pricing model", "discounted cash flow", "covariance", "correlation",
                 "alpha", "beta", "duration", "convexity", "inflation", "exchange traded fund"):
        if re.search(r"\b" + re.escape(term) + r"\b", text):
            return term
    text = re.sub(r"^(?:what (?:does|is|are)|how (?:does|do)|explain|tell me about|define)\s+", "", text)
    text = re.split(r"\b(?:mean|means|in|for|my|our|your|account|and what|and how)\b", text, maxsplit=1)[0]
    return " ".join(re.findall(r"[a-z]+(?:-[a-z]+)?", text)[:8])[:100]


def lookup(question):
    topic = search_topic(question)
    result = {"query": topic, "sources": [], "status": "unavailable",
              "google_search_url": "https://www.google.com/search?" + urlencode({"q": topic + " finance definition"})}
    if not topic:
        return result
    try:
        with httpx.Client(timeout=httpx.Timeout(5, connect=3), follow_redirects=False) as client:
            response = client.get(ENDPOINT, params={"q": topic, "format": "json", "no_html": 1, "no_redirect": 1},
                                  headers={"User-Agent": "FinPilot-Learn/1.0"})
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            return result
        summary = payload.get("AbstractText") or payload.get("Definition")
        url = payload.get("AbstractURL") or payload.get("DefinitionURL") or ""
        parsed = urlsplit(url)
        allowed = ("wikipedia.org", "investopedia.com", "cfainstitute.org", "investor.gov", "finra.org", "britannica.com")
        if isinstance(summary, str) and summary and parsed.scheme == "https" and any(
            parsed.hostname == host or (parsed.hostname or "").endswith("." + host) for host in allowed
        ):
            result["sources"] = [{"title": str(payload.get("Heading") or topic.title()), "url": url,
                                  "publisher": str(payload.get("AbstractSource") or payload.get("DefinitionSource") or parsed.hostname),
                                  "summary": " ".join(summary.split())[:1500]}]
            result["status"] = "found"
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    return result


def educational_evidence(research):
    # Keep definitions legible to the numeric-placeholder validator; dates and
    # sample numeric claims belong in separate server-computed example facts.
    references = []
    for source in research["sources"]:
        sentences = re.split(r"(?<=[.!?])\s+", source["summary"])
        text = " ".join(sentence for sentence in sentences if not re.search(r"\d", sentence))
        references.append({"title": source["title"], "definition": text or "Public reference available in source links."})
    evidence = {"general_finance_education": True, "topic": research["query"], "public_references": references,
                "web_reference_available": bool(references),
                "scope": "Explain concepts. Do not invent personal metrics, current market figures, sources or calculations."}
    if research["query"] == "sharpe ratio":
        evidence["verified_concept"] = "Sharpe ratio is excess return over a risk-free rate divided by return volatility, using the same time period."
        evidence["toy_example"] = {"portfolio_return_percent": 8, "risk_free_return_percent": 2,
                                   "volatility_percent": 12, "sharpe": (8 - 2) / 12,
                                   "label": "Illustrative assumptions, not this customer's portfolio"}
    return evidence


def clean_reply(reply):
    seen = set()
    def unique(text):
        parts = re.split(r"(?<=[.!?])(?:\s+|(?=[A-Z]))", text.strip())
        kept = []
        for part in parts:
            key = re.sub(r"\W+", " ", part).strip().casefold()
            if key and key not in seen:
                seen.add(key)
                kept.append(part.strip())
        return " ".join(kept)
    return {**reply, "answer": unique(reply["answer"]),
            "reasons": [item for text in reply["reasons"] if (item := unique(text))],
            "limitations": [item for text in reply["limitations"] if (item := unique(text))]}
