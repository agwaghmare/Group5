import json
from datetime import date

from app.core.db import SessionContext, db_session
from app.pnc.features.snapshot import load_snapshot
from app.pnc.features.xray import build_xray

for cid in ("C001", "C002", "C005"):
    ctx = SessionContext(role="customer", actor_id=cid, customer_id=cid)
    with db_session(ctx) as c:
        x = build_xray(load_snapshot(c, cid, date(2026, 10, 31)))
    print(cid, json.dumps(x["overall"])[:200])
    for i in x["indicators"]:
        print("  ", i["id"], i["raw"], i["normalized"], i["status"])
# point in time: earlier as_of must differ
with db_session(SessionContext(role="customer", actor_id="C001", customer_id="C001")) as c:
    x = build_xray(load_snapshot(c, "C001", date(2025, 6, 30)))
print("2025-06-30", x["overall"]["score"], [i["status"] for i in x["indicators"]])
