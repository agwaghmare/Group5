"""Local Solana wallet: network guards, $200/$500 limits, split-bill math. No live validator required."""
from __future__ import annotations

import json

import pytest

from app.solana.limits import split_bill, sol_to_usd, validate_payment, PAYMENT_REQUEST_LIMIT_USD, DAILY_PAYMENT_LIMIT_USD


def test_split_bill_divides_equally_and_preserves_total():
    entries = split_bill(3, ["alice", "bob", "charlie"])
    assert len(entries) == 3
    assert sum(e["amount"] for e in entries) == pytest.approx(3, abs=1e-9)
    assert entries[0]["recipient"] == "alice"


def test_split_bill_empty_and_single():
    assert split_bill(10, []) == []
    one = split_bill(7.77, ["solo"])
    assert one[0]["amount"] == pytest.approx(7.77)
    assert one[0]["share"] == 1


def test_validate_payment_rejects_over_200():
    limit_sol = PAYMENT_REQUEST_LIMIT_USD / 25
    result = validate_payment(limit_sol + 0.01, sender_balance=100, daily_total_usd=0, recent=[], recipient="x")
    assert result["ok"] is False
    assert "$200" in result["error"]


def test_validate_payment_allows_exact_200():
    limit_sol = PAYMENT_REQUEST_LIMIT_USD / 25
    result = validate_payment(limit_sol, sender_balance=100, daily_total_usd=0, recent=[], recipient="x")
    assert result["ok"] is True


def test_validate_payment_daily_limit_and_insufficient():
    over_daily = validate_payment(1, sender_balance=100, daily_total_usd=490, recent=[], recipient="x")
    assert over_daily["ok"] is False
    assert "Daily" in over_daily["error"]
    broke = validate_payment(5, sender_balance=3, daily_total_usd=0, recent=[], recipient="x")
    assert broke["ok"] is False
    assert "Insufficient" in broke["error"]


def test_validate_payment_warnings_and_duplicate():
    recent = [{"status": "confirmed", "amount": 1, "recipient": "bob", "timestamp": 10**13}]
    dup = validate_payment(1, sender_balance=100, daily_total_usd=0, recent=recent, recipient="bob")
    assert dup["ok"] is True
    assert any("5 minutes" in w for w in dup["warnings"])
    large = validate_payment(5, sender_balance=100, daily_total_usd=0, recent=[], recipient="x")
    assert any("$100" in w for w in large["warnings"])


def test_sol_to_usd_simulated_price():
    assert sol_to_usd(1) == 25
    assert sol_to_usd(8) == PAYMENT_REQUEST_LIMIT_USD
    assert DAILY_PAYMENT_LIMIT_USD == 500


def test_mainnet_is_refused(monkeypatch, tmp_path):
    from app.core import config
    from app.solana import service

    config.get_settings.cache_clear()
    monkeypatch.setenv("SOLANA_NETWORK", "mainnet-beta")
    monkeypatch.setenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    monkeypatch.setenv("SOLANA_KEYPAIR_PATH", str(tmp_path / "kp.json"))
    config.get_settings.cache_clear()
    with pytest.raises(service.SolanaError, match="Mainnet"):
        service.status()
    config.get_settings.cache_clear()


def test_status_reports_unreachable_localnet(monkeypatch, tmp_path):
    from app.core import config
    from app.solana import service

    monkeypatch.setenv("SOLANA_NETWORK", "localnet")
    monkeypatch.setenv("SOLANA_RPC_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("SOLANA_KEYPAIR_PATH", str(tmp_path / "kp.json"))
    config.get_settings.cache_clear()
    body = service.status("test-user")
    assert body["network"] == "localnet"
    assert body["reachable"] is False
    assert body["phantom_required"] is False
    assert body["signing"] == "server"
    assert "will not appear on public Devnet Explorer" in body["note"]
    assert (tmp_path / "kp.json").exists()
    secret = json.loads((tmp_path / "kp.json").read_text())
    assert isinstance(secret, list)
    config.get_settings.cache_clear()


def test_health_solana_endpoint(monkeypatch):
    from fastapi.testclient import TestClient

    from app.core import config
    from app.main import app

    monkeypatch.setenv("SOLANA_NETWORK", "localnet")
    monkeypatch.setenv("SOLANA_RPC_URL", "http://127.0.0.1:1")
    config.get_settings.cache_clear()
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health/solana")
    assert response.status_code == 200
    assert response.json()["network"] == "localnet"
    config.get_settings.cache_clear()


def test_wallet_routes_registered_and_require_session():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.orm.identity import current_identity
    from fastapi import HTTPException

    def denied():
        raise HTTPException(401, "Missing session")

    app.dependency_overrides[current_identity] = denied
    try:
        client = TestClient(app)
        for path in ("status", "history"):
            assert client.get(f"/api/v1/solana/{path}").status_code == 401
        for path in ("airdrop", "send", "split", "tokens", "tokens/transfer"):
            assert client.post(f"/api/v1/solana/{path}", json={}).status_code == 401
    finally:
        app.dependency_overrides.pop(current_identity, None)


def test_confirmation_waits_for_confirmed_status(monkeypatch):
    from app.solana import service

    states = iter([None, {"err": None, "confirmationStatus": "processed"},
                   {"err": None, "confirmationStatus": "confirmed"}])
    calls = []

    def rpc(method, params, **kwargs):
        calls.append((method, params))
        return {"value": [next(states)]}

    monkeypatch.setattr(service, "rpc", rpc)
    monkeypatch.setattr(service.time, "sleep", lambda _: None)
    service._confirm("test-signature")
    assert len(calls) == 3
    assert all(method == "getSignatureStatuses" for method, _ in calls)
    assert calls[0][1] == [["test-signature"], {"searchTransactionHistory": True}]


def test_confirmation_rejects_failed_transaction(monkeypatch):
    from app.solana import service

    monkeypatch.setattr(service, "rpc", lambda *a, **kw: {"value": [{"err": "InsufficientFunds", "confirmationStatus": "confirmed"}]})
    with pytest.raises(service.SolanaError, match="failed"):
        service._confirm("failed-signature")


def test_confirmation_timeout_does_not_report_success(monkeypatch):
    from app.solana import service

    with pytest.raises(service.SolanaError, match="still pending") as exc:
        service._confirm("pending-signature", timeout=0)
    assert exc.value.status_code == 504
