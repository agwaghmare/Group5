"""Opt-in real local-validator test: SOLANA_INTEGRATION=1 python -m pytest tests/test_solana_integration.py."""
import os

import pytest


@pytest.mark.skipif(os.environ.get("SOLANA_INTEGRATION") != "1", reason="Requires a running local Solana validator")
def test_authenticated_wallet_round_trip(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from solders.keypair import Keypair

    from app.core.config import get_settings
    from app.main import app
    from app.orm.accounts import update_account
    from app.orm.models import User
    from app.solana import service
    from app.staff.store import Store
    import secrets

    monkeypatch.setenv("SOLANA_NETWORK", "localnet")
    monkeypatch.setenv("SOLANA_RPC_URL", "http://127.0.0.1:8899")
    monkeypatch.setenv("SOLANA_KEYPAIR_PATH", str(tmp_path / "keypair.json"))
    monkeypatch.setattr(service, "_ledger_path", lambda: tmp_path / "ledger.json")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        password = secrets.token_urlsafe(24)
        with Store() as store:
            user = store.db.get(User, "U1000")
            update_account(store, user, "wallet-test@example.test", password)
        login = client.post("/api/v1/auth/login", json={"email": "wallet-test@example.test", "password": password})
        assert login.status_code == 200, login.text
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

        def request(method, path, **kwargs):
            response = client.request(method, "/api/v1/solana/" + path, **kwargs)
            assert response.status_code == 200, response.text
            return response.json()

        assert request("GET", "status")["reachable"] is True
        assert request("POST", "airdrop", json={"amount": 5})["balance_sol"] == 5
        recipient = str(Keypair().pubkey())
        payment = request("POST", "send", json={"recipient": recipient, "amount": 0.01})
        assert payment["status"] == "confirmed"
        assert service._balance_sol(service.Pubkey.from_string(recipient)) == pytest.approx(0.01)
        split = request("POST", "split", json={"recipients": [recipient, str(Keypair().pubkey())], "amount": 0.02})
        assert len(split["payments"]) == 2
        token = request("POST", "tokens", json={"name": "Connection test", "symbol": "TEST", "decimals": 6, "supply": 100})
        transfer = request("POST", "tokens/transfer", json={"mint": token["mint_address"], "recipient": recipient, "amount": 2, "decimals": 6})
        assert transfer["status"] == "confirmed"
        history = request("GET", "history")
        assert len(history["payments"]) == 3
        assert len(history["tokens"]) == len(history["transfers"]) == 1
    finally:
        get_settings.cache_clear()
