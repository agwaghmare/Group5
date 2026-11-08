import json
from datetime import date

from app.core.db import SessionContext, db_session
from app.pnc.features.snapshot import load_snapshot
from app.pnc.features.xray import build_xray

arch = json.load(open("../data/lab_package_demo/history_manifest.json"))["generator_archetypes"]
rows = []
for i in range(1, 31):
    cid = f"C{i:03d}"
    with db_session(SessionContext(role="customer", actor_id=cid, customer_id=cid)) as c:
        x = build_xray(load_snapshot(c, cid, date(2026, 10, 31)))
    d = {k["id"]: k["raw"] for k in x["indicators"]}
    rows.append((cid, arch[cid], x["overall"]["score"], d["savings_rate"], d["emergency_fund_months"], d["cash_flow_surplus_ratio"], d["debt_to_income"], d["credit_utilization"]))
for r in rows:
    print(r)
