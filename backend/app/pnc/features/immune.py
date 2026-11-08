"""fin.immune: shock-resilience testing (deterministic) plus an optional, clearly labelled Markov view."""
from __future__ import annotations

from decimal import Decimal

import numpy as np

from app.pnc.finance import engine as E

from .snapshot import Snapshot

D = Decimal
SHOCKS = {
    "job_loss": dict(income_drop_pct=D("1.0"), expense_increase_pct=D("0"), one_time_shock=D("0"), label="Total loss of income"),
    "income_cut_30": dict(income_drop_pct=D("0.30"), expense_increase_pct=D("0"), one_time_shock=D("0"), label="30% income reduction"),
    "expense_spike_20": dict(income_drop_pct=D("0"), expense_increase_pct=D("0.20"), one_time_shock=D("0"), label="Essential costs up 20%"),
    "medical_bill": dict(income_drop_pct=D("0"), expense_increase_pct=D("0"), one_time_shock=D("5000"), label="One-time $5,000 expense"),
    "combined": dict(income_drop_pct=D("0.30"), expense_increase_pct=D("0.10"), one_time_shock=D("2500"), label="30% income cut + 10% costs + $2,500"),
}


def run_shocks(snap: Snapshot, overrides: dict | None = None) -> dict:
    inc, ess, debt = snap.avg("income", 6), snap.avg("essential_spending", 6), snap.avg("debt_payments", 6)
    if None in (inc, ess, debt):
        return {"as_of": snap.as_of.isoformat(), "shocks": [], "missing_inputs": ["6 months of income/essential/debt history"]}
    liquid = snap.sum_balance({"checking", "savings"})
    shocks = {**SHOCKS, **(overrides or {})}
    out = []
    for key, s in shocks.items():
        ev = E.calc_stress_test(snap.as_of, liquid, inc, ess, debt, s["income_drop_pct"], s["expense_increase_pct"], s["one_time_shock"],
                                source="pnc_demo_data")
        runway = ev.results["runway_months"]
        status = ("strong" if ev.results["status"] == "self_funding" or (runway is not None and D(runway) >= 6)
                  else "ok" if D(runway) >= 3 else "watch" if D(runway) >= 1 else "risk")
        out.append({"shock": key, "label": s["label"], "status": status, "runway_months": runway,
                    "evidence": ev.model_dump(mode="json")})
    order = {"risk": 0, "watch": 1, "ok": 2, "strong": 3}
    worst = min(out, key=lambda r: order[r["status"]])
    return {"as_of": snap.as_of.isoformat(), "starting_liquidity": str(E.money(liquid)), "shocks": out,
            "weakest_scenario": worst["shock"], "thresholds": {"strong": ">= 6 months or self-funding", "ok": ">= 3", "watch": ">= 1", "risk": "< 1"},
            "disclaimer": "Hypothetical stress tests on your own data; not predictions."}


STATES = ["comfortable", "tight", "strained"]


def markov_view(snap: Snapshot, steps: int = 3) -> dict:
    """EXPERIMENTAL: per-customer 3-state chain from monthly surplus ratio. Small sample (<= 23 transitions)."""
    m = snap.monthly
    if len(m) < 8:
        return {"available": False, "missing_inputs": ["8+ months of cash-flow history"]}
    ratio = ((m.income.astype(float) - m.consumption_spending.astype(float) - m.debt_payments.astype(float)) / m.income.astype(float).replace(0, np.nan)).fillna(-1)
    seq = [0 if r >= 0.10 else 1 if r >= 0.0 else 2 for r in ratio]
    counts = np.ones((3, 3)) * 0.5          # Laplace smoothing
    for a, b in zip(seq[:-1], seq[1:]):
        counts[a, b] += 1
    P = counts / counts.sum(axis=1, keepdims=True)
    dist = np.zeros(3); dist[seq[-1]] = 1
    for _ in range(steps):
        dist = dist @ P
    return {"available": True, "label": "EXPERIMENTAL - small-sample illustration, not a forecast", "states": STATES,
            "state_rule": "comfortable: surplus >= 10% of income; tight: 0-10%; strained: < 0", "current_state": STATES[seq[-1]],
            "transition_matrix": [[round(float(x), 3) for x in row] for row in P], "sample_transitions": len(seq) - 1,
            f"state_distribution_after_{steps}_months": {s: round(float(p), 3) for s, p in zip(STATES, dist)}}
