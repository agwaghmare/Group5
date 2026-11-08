"""Customer Solana localnet/Devnet endpoints. SQLAlchemy identity is unchanged."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.orm.identity import current_identity
from app.solana import service

router = APIRouter(prefix="/api/v1/solana", tags=["Solana wallet"])


class SendBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipient: str = Field(min_length=32, max_length=64)
    amount: float = Field(gt=0)
    note: str | None = Field(default=None, max_length=200)


class SplitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipients: list[str] = Field(min_length=2, max_length=20)
    amount: float = Field(gt=0)


class AirdropBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: float = Field(default=100, gt=0, le=1000)


class TokenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=10)
    decimals: int = Field(default=9, ge=0, le=18)
    supply: float = Field(gt=0)


class TransferBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mint: str = Field(min_length=32, max_length=64)
    recipient: str = Field(min_length=32, max_length=64)
    amount: float = Field(gt=0)
    decimals: int = Field(default=9, ge=0, le=18)


def _run(fn):
    try:
        return fn()
    except service.SolanaError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


def _user_id(store) -> str:
    return store.user.id


@router.get("/status")
def solana_status(store=Depends(current_identity)):
    store.audit("solana_status")
    return _run(lambda: service.status(_user_id(store)))


@router.post("/airdrop")
def solana_airdrop(body: AirdropBody, store=Depends(current_identity)):
    store.audit("solana_airdrop")
    return _run(lambda: service.airdrop(body.amount))


@router.post("/send")
def solana_send(body: SendBody, store=Depends(current_identity)):
    store.audit("solana_send")
    return _run(lambda: service.send_sol(_user_id(store), body.recipient, body.amount, body.note))


@router.post("/split")
def solana_split(body: SplitBody, store=Depends(current_identity)):
    store.audit("solana_split")
    return _run(lambda: service.send_split(_user_id(store), body.recipients, body.amount))


@router.post("/tokens")
def solana_create_token(body: TokenBody, store=Depends(current_identity)):
    store.audit("solana_create_token")
    return _run(lambda: service.create_token(_user_id(store), body.name, body.symbol, body.decimals, body.supply))


@router.post("/tokens/transfer")
def solana_transfer_token(body: TransferBody, store=Depends(current_identity)):
    store.audit("solana_transfer_token")
    return _run(lambda: service.transfer_token(_user_id(store), body.mint, body.recipient, body.amount, body.decimals))


@router.get("/history")
def solana_history(store=Depends(current_identity)):
    store.audit("solana_history")
    return _run(service.history)
