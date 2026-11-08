"""JSON-RPC client for a local Solana validator or public Devnet.

The server signs with a gitignored test keypair so CoinForge and payments work
without Phantom. Mainnet is refused. Test SOL has no real monetary value.
"""
from __future__ import annotations

import base64
import json
import struct
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import CreateAccountParams, TransferParams, create_account, transfer
from solders.transaction import Transaction

from app.core.config import BACKEND_DIR, get_settings
from app.solana.limits import (
    DAILY_PAYMENT_LIMIT_USD,
    PAYMENT_REQUEST_LIMIT_USD,
    SOL_SIMULATED_PRICE_USD,
    sol_to_usd,
    split_bill,
    validate_payment,
)

LAMPORTS_PER_SOL = 1_000_000_000
MAX_TOKEN_UNITS = 2**64 - 1
MINT_SIZE = 82
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
ASSOCIATED_TOKEN_PROGRAM_ID = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
SYSTEM_PROGRAM_ID = Pubkey.from_string("11111111111111111111111111111111")
ALLOWED_NETWORKS = {"localnet", "devnet", "testnet"}
FORBIDDEN_NETWORKS = {"mainnet", "mainnet-beta"}


class SolanaError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _network() -> str:
    settings = get_settings()
    network = (settings.solana_network or "localnet").strip().lower()
    if network in FORBIDDEN_NETWORKS:
        raise SolanaError("Mainnet is disabled. FinPilot uses localnet or Devnet test SOL only.", 403)
    if network not in ALLOWED_NETWORKS:
        raise SolanaError(f"Unsupported Solana network '{network}'. Use localnet or devnet.", 400)
    return network


def rpc_url() -> str:
    return (get_settings().solana_rpc_url or "http://127.0.0.1:8899").rstrip("/")


def _keypair_path() -> Path:
    raw = get_settings().solana_keypair_path
    path = Path(raw)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path


def load_or_create_keypair() -> Keypair:
    path = _keypair_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return Keypair.from_json(path.read_text(encoding="utf-8"))
    keypair = Keypair()
    path.write_text(keypair.to_json(), encoding="utf-8")
    return keypair


def _ledger_path() -> Path:
    return BACKEND_DIR / "storage" / "solana_ledger.json"


def _read_ledger() -> dict:
    path = _ledger_path()
    if not path.exists():
        return {"daily": {"date": "", "by_user": {}}, "payments": [], "tokens": [], "transfers": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"daily": {"date": "", "by_user": {}}, "payments": [], "tokens": [], "transfers": []}


def _write_ledger(data: dict) -> None:
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def rpc(method: str, params: list | None = None, timeout: float = 30.0) -> dict | list | str | int | None:
    try:
        response = httpx.post(
            rpc_url(),
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise SolanaError(f"Cannot reach Solana RPC at {rpc_url()}: {exc.__class__.__name__}", 503) from exc
    if "error" in payload:
        message = payload["error"].get("message") if isinstance(payload["error"], dict) else str(payload["error"])
        raise SolanaError(message or "Solana RPC error", 502)
    return payload.get("result")


def ping() -> bool:
    try:
        rpc("getHealth", timeout=4.0)
        return True
    except SolanaError:
        return False


def explorer_note(network: str) -> str:
    if network == "localnet":
        return "Local test validator. Transactions stay on this machine and will not appear on public Devnet Explorer. Test SOL has no real value."
    return "Public Devnet. Test SOL only — no real dollar value. Explorer links use cluster=devnet."


def status(user_id: str | None = None) -> dict:
    network = _network()
    keypair = load_or_create_keypair()
    reachable = ping()
    balance = None
    if reachable:
        try:
            balance = _balance_sol(keypair.pubkey())
        except SolanaError:
            reachable = False
    daily = _daily_total(user_id or "anon")
    return {
        "network": network,
        "rpc_url": rpc_url(),
        "reachable": reachable,
        "signing": "server",
        "phantom_required": False,
        "public_key": str(keypair.pubkey()),
        "balance_sol": balance,
        "estimated_usd": None if balance is None else sol_to_usd(balance),
        "note": explorer_note(network),
        "limits": {
            "per_request_usd": PAYMENT_REQUEST_LIMIT_USD,
            "daily_usd": DAILY_PAYMENT_LIMIT_USD,
            "daily_spent_usd": daily,
            "sol_simulated_price_usd": SOL_SIMULATED_PRICE_USD,
        },
    }


def _balance_sol(pubkey: Pubkey) -> float:
    result = rpc("getBalance", [str(pubkey), {"commitment": "confirmed"}])
    value = result.get("value") if isinstance(result, dict) else result
    return int(value or 0) / LAMPORTS_PER_SOL


def _blockhash() -> Hash:
    result = rpc("getLatestBlockhash", [{"commitment": "confirmed"}])
    if not isinstance(result, dict):
        raise SolanaError("Missing blockhash from RPC", 502)
    value = result.get("value") or result
    return Hash.from_string(value["blockhash"])


def _send(tx: Transaction) -> str:
    raw = base64.b64encode(bytes(tx)).decode("ascii")
    signature = rpc("sendTransaction", [raw, {"encoding": "base64", "skipPreflight": False, "preflightCommitment": "confirmed"}])
    if not isinstance(signature, str):
        raise SolanaError("RPC did not return a signature", 502)
    _confirm(signature)
    return signature


def _confirm(signature: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SolanaError(f"Transaction {signature} is still pending. Check its status before retrying.", 504)
        result = rpc("getSignatureStatuses", [[signature], {"searchTransactionHistory": True}], timeout=min(4.0, remaining))
        values = result.get("value") if isinstance(result, dict) else None
        state = values[0] if values else None
        if state:
            if state.get("err") is not None:
                raise SolanaError(f"Transaction {signature} failed: {state['err']}", 502)
            if state.get("confirmationStatus") in {"confirmed", "finalized"}:
                return
        time.sleep(min(0.25, max(0, deadline - time.monotonic())))


def airdrop(amount_sol: float = 100.0) -> dict:
    network = _network()
    if amount_sol <= 0:
        raise SolanaError("Airdrop amount must be positive")
    cap = 1000.0 if network == "localnet" else 2.0
    if amount_sol > cap:
        raise SolanaError(f"Airdrop cap on {network} is {cap:g} SOL")
    keypair = load_or_create_keypair()
    lamports = int(amount_sol * LAMPORTS_PER_SOL)
    signature = rpc("requestAirdrop", [str(keypair.pubkey()), lamports])
    if not isinstance(signature, str):
        raise SolanaError("RPC did not return an airdrop signature", 502)
    _confirm(signature)
    return {
        "network": network,
        "public_key": str(keypair.pubkey()),
        "requested_sol": amount_sol,
        "signature": signature,
        "balance_sol": _balance_sol(keypair.pubkey()),
        "note": "Test SOL only. No real monetary value.",
    }


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _daily_total(user_id: str) -> float:
    ledger = _read_ledger()
    daily = ledger.get("daily") or {}
    if daily.get("date") != _today():
        return 0.0
    return float((daily.get("by_user") or {}).get(user_id, 0.0))


def _record_payment(user_id: str, payment: dict) -> None:
    ledger = _read_ledger()
    today = _today()
    daily = ledger.get("daily") or {"date": "", "by_user": {}}
    if daily.get("date") != today:
        daily = {"date": today, "by_user": {}}
    by_user = daily.setdefault("by_user", {})
    by_user[user_id] = float(by_user.get(user_id, 0.0)) + float(payment["estimated_usd"])
    ledger["daily"] = daily
    payments = ledger.setdefault("payments", [])
    payments.insert(0, payment)
    ledger["payments"] = payments[:200]
    _write_ledger(ledger)


def send_sol(user_id: str, recipient: str, amount: float, note: str | None = None) -> dict:
    _network()
    keypair = load_or_create_keypair()
    try:
        dest = Pubkey.from_string(recipient.strip())
    except ValueError as exc:
        raise SolanaError("Invalid recipient address") from exc
    balance = _balance_sol(keypair.pubkey())
    check = validate_payment(amount, balance, _daily_total(user_id), _read_ledger().get("payments") or [], str(dest))
    if not check["ok"]:
        raise SolanaError(check["error"])
    lamports = int(round(amount * LAMPORTS_PER_SOL))
    ix = transfer(TransferParams(from_pubkey=keypair.pubkey(), to_pubkey=dest, lamports=lamports))
    tx = Transaction.new_signed_with_payer([ix], keypair.pubkey(), [keypair], _blockhash())
    signature = _send(tx)
    payment = {
        "id": signature,
        "sender": str(keypair.pubkey()),
        "recipient": str(dest),
        "amount": amount,
        "token": "SOL",
        "estimated_usd": check["estimated_usd"],
        "status": "confirmed",
        "signature": signature,
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
        "note": note,
        "warnings": check["warnings"],
        "network": _network(),
    }
    _record_payment(user_id, payment)
    payment["balance_sol"] = _balance_sol(keypair.pubkey())
    return payment


def send_split(user_id: str, recipients: list[str], total_amount: float) -> dict:
    entries = split_bill(total_amount, [item.strip() for item in recipients if item.strip()])
    if len(entries) < 2:
        raise SolanaError("Enter at least 2 addresses to split between")
    sent = []
    for entry in entries:
        sent.append(send_sol(user_id, entry["recipient"], entry["amount"], note=f"Split bill: {entry['amount']} SOL"))
    return {"status": "confirmed", "payments": sent, "total": total_amount, "recipients": len(entries)}


def _associated_token_address(owner: Pubkey, mint: Pubkey) -> Pubkey:
    return Pubkey.find_program_address(
        [bytes(owner), bytes(TOKEN_PROGRAM_ID), bytes(mint)],
        ASSOCIATED_TOKEN_PROGRAM_ID,
    )[0]


def raw_units(amount: float, decimals: int) -> int:
    """Smallest token units. Solana stores this as a 64-bit whole number."""
    if decimals < 0 or decimals > 18:
        raise SolanaError("Decimals must be 0–18")
    if amount <= 0:
        raise SolanaError("Amount must be positive")
    text = format(amount, "f")
    whole, _, frac = text.partition(".")
    frac = (frac[:decimals]).ljust(decimals, "0")
    try:
        units = int(whole) * (10**decimals) + (int(frac) if frac else 0)
    except ValueError as exc:
        raise SolanaError("Amount must be a plain number") from exc
    if units <= 0 or units > MAX_TOKEN_UNITS:
        largest = MAX_TOKEN_UNITS / (10**decimals)
        raise SolanaError(
            f"That amount does not fit in a Solana coin with {decimals} decimals. "
            f"Use at most {largest:,.0f}, or fewer decimals."
        )
    return units


def _initialize_mint_ix(mint: Pubkey, decimals: int, authority: Pubkey) -> Instruction:
    data = bytes([20, decimals]) + bytes(authority) + bytes([0])
    return Instruction(TOKEN_PROGRAM_ID, data, [AccountMeta(mint, is_signer=False, is_writable=True)])


def _create_ata_ix(payer: Pubkey, owner: Pubkey, mint: Pubkey) -> Instruction:
    ata = _associated_token_address(owner, mint)
    return Instruction(
        ASSOCIATED_TOKEN_PROGRAM_ID,
        bytes([1]),
        [
            AccountMeta(payer, is_signer=True, is_writable=True),
            AccountMeta(ata, is_signer=False, is_writable=True),
            AccountMeta(owner, is_signer=False, is_writable=False),
            AccountMeta(mint, is_signer=False, is_writable=False),
            AccountMeta(SYSTEM_PROGRAM_ID, is_signer=False, is_writable=False),
            AccountMeta(TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
        ],
    )


def _mint_to_ix(mint: Pubkey, dest: Pubkey, authority: Pubkey, amount: int) -> Instruction:
    data = bytes([7]) + struct.pack("<Q", amount)
    return Instruction(
        TOKEN_PROGRAM_ID,
        data,
        [
            AccountMeta(mint, is_signer=False, is_writable=True),
            AccountMeta(dest, is_signer=False, is_writable=True),
            AccountMeta(authority, is_signer=True, is_writable=False),
        ],
    )


def _transfer_ix(source: Pubkey, dest: Pubkey, owner: Pubkey, amount: int) -> Instruction:
    data = bytes([3]) + struct.pack("<Q", amount)
    return Instruction(
        TOKEN_PROGRAM_ID,
        data,
        [
            AccountMeta(source, is_signer=False, is_writable=True),
            AccountMeta(dest, is_signer=False, is_writable=True),
            AccountMeta(owner, is_signer=True, is_writable=False),
        ],
    )


def create_token(user_id: str, name: str, symbol: str, decimals: int, initial_supply: float) -> dict:
    _network()
    name = name.strip()
    symbol = symbol.strip().upper()
    if not name or not symbol:
        raise SolanaError("Name and symbol are required")
    if decimals < 0 or decimals > 18:
        raise SolanaError("Decimals must be 0–18")
    if initial_supply <= 0:
        raise SolanaError("Supply must be positive")
    payer = load_or_create_keypair()
    mint = Keypair()
    rent = rpc("getMinimumBalanceForRentExemption", [MINT_SIZE])
    lamports = int(rent if isinstance(rent, int) else (rent or 0))
    ata = _associated_token_address(payer.pubkey(), mint.pubkey())
    raw_supply = raw_units(initial_supply, decimals)
    ixs = [
        create_account(
            CreateAccountParams(
                from_pubkey=payer.pubkey(),
                to_pubkey=mint.pubkey(),
                lamports=lamports,
                space=MINT_SIZE,
                owner=TOKEN_PROGRAM_ID,
            )
        ),
        _initialize_mint_ix(mint.pubkey(), decimals, payer.pubkey()),
        _create_ata_ix(payer.pubkey(), payer.pubkey(), mint.pubkey()),
        _mint_to_ix(mint.pubkey(), ata, payer.pubkey(), raw_supply),
    ]
    tx = Transaction.new_signed_with_payer(ixs, payer.pubkey(), [payer, mint], _blockhash())
    signature = _send(tx)
    token = {
        "mint_address": str(mint.pubkey()),
        "name": name,
        "symbol": symbol,
        "decimals": decimals,
        "supply": initial_supply,
        "created_at": int(datetime.now(timezone.utc).timestamp() * 1000),
        "creator": str(payer.pubkey()),
        "signature": signature,
        "network": _network(),
        "note": "Custom SPL token on a test cluster. No real dollar value.",
    }
    ledger = _read_ledger()
    tokens = ledger.setdefault("tokens", [])
    tokens.insert(0, token)
    ledger["tokens"] = tokens[:100]
    _write_ledger(ledger)
    return token


def transfer_token(user_id: str, mint_address: str, recipient: str, amount: float, decimals: int) -> dict:
    _network()
    if amount <= 0:
        raise SolanaError("Amount must be positive")
    payer = load_or_create_keypair()
    try:
        mint = Pubkey.from_string(mint_address.strip())
        dest_owner = Pubkey.from_string(recipient.strip())
    except ValueError as exc:
        raise SolanaError("Invalid mint or recipient address") from exc
    source = _associated_token_address(payer.pubkey(), mint)
    dest = _associated_token_address(dest_owner, mint)
    raw = raw_units(amount, decimals)
    ixs = [_create_ata_ix(payer.pubkey(), dest_owner, mint), _transfer_ix(source, dest, payer.pubkey(), raw)]
    tx = Transaction.new_signed_with_payer(ixs, payer.pubkey(), [payer], _blockhash())
    signature = _send(tx)
    record = {
        "id": signature,
        "mint": str(mint),
        "from": str(payer.pubkey()),
        "to": str(dest_owner),
        "amount": amount,
        "signature": signature,
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
        "status": "confirmed",
        "network": _network(),
    }
    ledger = _read_ledger()
    transfers = ledger.setdefault("transfers", [])
    transfers.insert(0, record)
    ledger["transfers"] = transfers[:200]
    _write_ledger(ledger)
    return record


def history() -> dict:
    ledger = _read_ledger()
    return {
        "payments": ledger.get("payments") or [],
        "tokens": ledger.get("tokens") or [],
        "transfers": ledger.get("transfers") or [],
        "network": _network(),
    }
