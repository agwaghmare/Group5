"""Background job: persist each customer's financial-health indicators as of a date (`pnc_health_snapshots`).

Runs as the table owner (pipeline/job context), never inside a customer request. Idempotent per (customer, as_of).
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import text

from app.core.db import db_session
from app.pnc.features.snapshot import load_snapshot
from app.pnc.features.xray import build_xray


def build_snapshots(as_of: date) -> dict:
    written = 0
    with db_session() as s:
        custs = [r[0] for r in s.execute(text("SELECT customer_id FROM pnc_customers ORDER BY 1"))]
        for cid in custs:
            x = build_xray(load_snapshot(s, cid, as_of))
            s.execute(text("INSERT INTO pnc_health_snapshots(customer_id, as_of, features, indicators, engine_version) "
                           "VALUES (:c,:a,CAST(:f AS jsonb),CAST(:i AS jsonb),:v) ON CONFLICT DO NOTHING"),
                      {"c": cid, "a": as_of, "f": json.dumps({"overall": x["overall"]}),
                       "i": json.dumps(x["indicators"], default=str), "v": x["engine_version"]})
            written += 1
    return {"as_of": as_of.isoformat(), "customers": written}
