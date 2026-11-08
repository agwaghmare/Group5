"""Scratch runner for the data pipeline (the supported entry point is the `pnc` CLI)."""
import json

from app.pnc.data import pipeline

print(json.dumps(pipeline.ingest(), indent=1, default=str))
rec = pipeline.reconcile()
for c in rec["checks"]:
    print("PASS" if c["passed"] else "FAIL", c["check"], c["detail"])
print("gold:", pipeline.build_gold())
