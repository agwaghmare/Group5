import httpx
import pytest

from app.services import learning_web


@pytest.mark.parametrize("payload", [[], {"AbstractText": "Unsafe", "AbstractURL": "http://localhost/admin"},
                                   {"AbstractText": "Unsafe", "AbstractURL": "https://wikipedia.org.evil.test/x"}])
def test_lookup_rejects_malformed_and_untrusted_sources(monkeypatch, payload):
    original = httpx.Client
    monkeypatch.setattr(learning_web.httpx, "Client", lambda **kw: original(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)), **kw))
    result = learning_web.lookup("Explain Sharpe ratio")
    assert result["status"] == "unavailable"
    assert result["sources"] == []


def test_lookup_uses_only_the_public_topic_and_returns_verified_link(monkeypatch):
    original = httpx.Client
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"AbstractText": "Sharpe ratio compares excess return with volatility.",
            "AbstractURL": "https://en.wikipedia.org/wiki/Sharpe_ratio", "Heading": "Sharpe ratio",
            "AbstractSource": "Wikipedia"})

    monkeypatch.setattr(learning_web.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    result = learning_web.lookup("What does Sharpe ratio mean for my $12345 account me@example.test?")
    assert requests[0].url.params["q"] == "sharpe ratio"
    assert "12345" not in str(requests[0].url) and "example.test" not in str(requests[0].url)
    assert result["status"] == "found"
    assert result["sources"][0]["url"] == "https://en.wikipedia.org/wiki/Sharpe_ratio"
    evidence = learning_web.educational_evidence(result)
    assert evidence["toy_example"]["sharpe"] == .5
    assert "recorded_numbers" not in evidence


def test_network_failure_allows_general_explanation(monkeypatch):
    original = httpx.Client

    def fail(request):
        raise httpx.ReadTimeout("offline", request=request)

    monkeypatch.setattr(learning_web.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(fail), **kw))
    result = learning_web.lookup("Explain covariance")
    assert result["status"] == "unavailable"
    assert learning_web.educational_evidence(result)["general_finance_education"] is True


def test_repeated_answer_and_reasons_are_removed():
    reply = learning_web.clean_reply({"answer": "Returns vary.Returns vary. Risk matters.",
        "reasons": ["Risk matters.", "Use matching periods."], "limitations": ["Use matching periods."]})
    assert reply["answer"] == "Returns vary. Risk matters."
    assert reply["reasons"] == ["Use matching periods."]
    assert reply["limitations"] == []
