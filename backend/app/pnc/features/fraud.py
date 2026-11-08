"""fin.fraud customer side: view anomaly events, open a SIMULATED fraud case that creates a service case with only
consented context. An anomaly is never presented as confirmed fraud."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import Connection, text

from app.pnc.errors import NotFound

EVENT_COPY = ("This purchase looked unusual compared with your normal activity. That does not mean it is fraud. "
              "If you do not recognise it, you can report it below.")


def list_events(conn: Connection) -> list[dict]:
    rows = conn.execute(text(
        "SELECT event_id, transaction_id, posted_date, detector, anomaly_score, model_version, supporting_factors, review_status "
        "FROM pnc_fraud_events ORDER BY posted_date DESC, event_id")).mappings().all()
    return [{**dict(r), "event_id": str(r["event_id"]), "posted_date": r["posted_date"].isoformat(),
             "anomaly_score": None if r["anomaly_score"] is None else float(r["anomaly_score"]),
             "label": "unusual_activity_for_review", "explanation": EVENT_COPY, "confirmed_fraud": False} for r in rows]


def has_consent(conn: Connection, customer_id: str, scope: str = "case_context_sharing") -> bool:
    r = conn.execute(text("SELECT granted FROM pnc_consents WHERE customer_id = :c AND scope = :s"), {"c": customer_id, "s": scope}).first()
    return bool(r and r[0])


def create_case(conn: Connection, customer_id: str, transaction_id: str | None, reason: str, description: str | None,
                share_context: bool) -> dict:
    ctx: dict = {"consented": False}
    source = "transaction_report"
    if transaction_id:
        t = conn.execute(text("SELECT transaction_id, posted_date, category, amount FROM pnc_transactions WHERE transaction_id = :t"),
                         {"t": transaction_id}).mappings().first()
        if t is None:
            raise NotFound("transaction not found for this customer")
        ev = conn.execute(text("SELECT 1 FROM pnc_fraud_events WHERE transaction_id = :t LIMIT 1"), {"t": transaction_id}).first()
        if ev:
            source = "fraud_anomaly_investigation"
        if share_context:
            if not has_consent(conn, customer_id):
                raise PermissionError("context sharing requires a recorded consent (scope: case_context_sharing)")
            ctx = {"consented": True, "shared": {"transaction_id": t["transaction_id"], "posted_date": t["posted_date"].isoformat(),
                                                 "category": t["category"], "amount": str(t["amount"])},
                   "not_shared": ["balances", "other accounts", "credit information"]}
    elif share_context:
        raise ValueError("share_context requires a transaction_id")
    sla = datetime.now(timezone.utc) + timedelta(days=2)
    scid = conn.execute(text(
        "INSERT INTO cases(customer_id, source, reason, consented_context, status, sla_due) "
        "VALUES (:c,:s,:r,CAST(:x AS jsonb),'new',:sla) RETURNING case_id"),
        {"c": customer_id, "s": source, "r": reason, "x": json.dumps(ctx), "sla": sla}).scalar_one()
    fcid = conn.execute(text(
        "INSERT INTO pnc_fraud_cases(customer_id, transaction_id, reason, description, service_case_id) "
        "VALUES (:c,:t,:r,:d,:s) RETURNING case_id"),
        {"c": customer_id, "t": transaction_id, "r": reason, "d": description, "s": scid}).scalar_one()
    conn.execute(text("INSERT INTO pnc_fraud_case_history(case_id, customer_id, to_status, note) VALUES (:f,:c,'submitted','simulated report submitted')"),
                 {"f": fcid, "c": customer_id})
    return {"fraud_case_id": str(fcid), "service_case_id": str(scid), "status": "submitted", "simulated": True,
            "shared_context": ctx, "sla_due": sla.isoformat(),
            "message": "This is a simulated report for the demo. No real card action or investigation happens."}


def list_cases(conn: Connection) -> list[dict]:
    rows = conn.execute(text("SELECT case_id, transaction_id, reason, status, simulated, created_at FROM pnc_fraud_cases ORDER BY created_at DESC")).mappings().all()
    return [{**dict(r), "case_id": str(r["case_id"]), "created_at": r["created_at"].isoformat()} for r in rows]
