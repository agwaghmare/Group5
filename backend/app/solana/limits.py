"""In-app payment caps. Simulated USD only — test SOL has no real value."""
from __future__ import annotations

from datetime import datetime, timezone

PAYMENT_REQUEST_LIMIT_USD = 200.0
DAILY_PAYMENT_LIMIT_USD = 500.0
SOL_SIMULATED_PRICE_USD = 25.0
DUPLICATE_WINDOW_MS = 300_000


def sol_to_usd(sol: float) -> float:
    return sol * SOL_SIMULATED_PRICE_USD


def split_bill(total_amount: float, recipients: list[str]) -> list[dict]:
    if not recipients:
        return []
    share = total_amount / len(recipients)
    rounded = int(share * 1e9) / 1e9
    last_index = len(recipients) - 1
    return [
        {
            "recipient": recipient,
            "amount": total_amount - rounded * last_index if i == last_index else rounded,
            "share": 1 / len(recipients),
        }
        for i, recipient in enumerate(recipients)
    ]


def validate_payment(
    amount: float,
    sender_balance: float,
    daily_total_usd: float,
    recent: list[dict],
    recipient: str,
) -> dict:
    warnings: list[str] = []
    usd = sol_to_usd(amount)
    if amount <= 0:
        return {"ok": False, "error": "Amount must be positive", "warnings": warnings, "estimated_usd": usd}
    if usd > PAYMENT_REQUEST_LIMIT_USD:
        return {
            "ok": False,
            "error": f"Exceeds the ${PAYMENT_REQUEST_LIMIT_USD:.0f} per-request limit ({amount} SOL ≈ ${usd:.2f})",
            "warnings": warnings,
            "estimated_usd": usd,
        }
    if amount > sender_balance:
        return {
            "ok": False,
            "error": f"Insufficient balance (have {sender_balance:.4f} SOL)",
            "warnings": warnings,
            "estimated_usd": usd,
        }
    if daily_total_usd + usd > DAILY_PAYMENT_LIMIT_USD:
        return {
            "ok": False,
            "error": f"Daily limit of ${DAILY_PAYMENT_LIMIT_USD:.0f} reached (${daily_total_usd:.2f} already sent today)",
            "warnings": warnings,
            "estimated_usd": usd,
        }
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    for payment in recent:
        if (
            payment.get("status") == "confirmed"
            and payment.get("amount") == amount
            and payment.get("recipient") == recipient
            and now_ms - int(payment.get("timestamp") or 0) < DUPLICATE_WINDOW_MS
        ):
            warnings.append("A similar payment was sent in the last 5 minutes.")
            break
    if usd > 100:
        warnings.append("Large payment: over $100 equivalent.")
    if amount > sender_balance * 0.9:
        warnings.append("This will use over 90% of your balance.")
    return {"ok": True, "warnings": warnings, "estimated_usd": usd}
