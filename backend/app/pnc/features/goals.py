"""Savings goals: CRUD plus a deterministic plan calculator (fin.moneymission goals / SafeSpend inputs)."""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Connection, text

from app.pnc.finance import engine as E
from app.pnc.finance.evidence import make_evidence

from .snapshot import Snapshot

D = Decimal


class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_amount: Decimal = Field(gt=0)
    starting_amount: Decimal = Field(default=Decimal("0"), ge=0)
    deadline: date
    planned_monthly_contribution: Decimal | None = Field(default=None, ge=0)
    max_monthly_contribution: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _starting_not_above_target_ok(self):
        return self


def months_between(a: date, b: date) -> int:
    return max((b.year - a.year) * 12 + (b.month - a.month) + (1 if b.day >= a.day else 0), 0)


def calculate_plan(snap: Snapshot | None, goal: dict, as_of: date, annual_rate: Decimal = D("0")) -> dict:
    """Required monthly contribution, feasibility against the customer's average surplus, and alternatives."""
    target, current = D(str(goal["target_amount"])), D(str(goal["current_amount"]))
    months = months_between(as_of, goal["deadline"])
    ev = E.calc_goal_contribution(as_of, target, current, months, annual_rate)
    need = D(ev.results["required_monthly"]) if ev.results["required_monthly"] is not None else None
    surplus = None
    if snap is not None:
        inc, cons, debt = snap.avg("income", 6), snap.avg("consumption_spending", 6), snap.avg("debt_payments", 6)
        if None not in (inc, cons, debt):
            surplus = E.money(inc - cons - debt)
    cap = goal.get("max_monthly_contribution")
    cap = D(str(cap)) if cap is not None else None
    limit = min([x for x in (surplus if surplus and surplus > 0 else None, cap) if x is not None], default=None)
    res: dict = {"months_remaining": months, "required_monthly": ev.results["required_monthly"], "average_monthly_surplus": surplus,
                 "already_funded": ev.results["already_funded"], "progress_pct": float(min(current / target, D(1)) * 100)}
    if ev.results["already_funded"]:
        res["status"] = "funded"
    elif months <= 0:
        res["status"] = "deadline_passed"
    elif limit is None:
        res["status"] = "needs_surplus_data"
    elif need is not None and need <= limit:
        res["status"] = "on_track_feasible"
    else:
        res["status"] = "needs_adjustment"
        remaining = target - current
        if limit and limit > 0 and annual_rate == 0:
            res["alternative_deadline_months"] = int(math.ceil(float(remaining / limit)))
            res["alternative_monthly_at_limit"] = E.money(limit)
        res["alternative_target_at_deadline"] = E.money(current + (limit or D(0)) * months) if limit else None
    planned = goal.get("planned_monthly_contribution")
    if planned is not None and ev.results["required_monthly"] is not None:
        res["planned_vs_required_gap"] = E.money(D(str(planned)) - need)
    evidence = make_evidence("goal_plan", as_of, {"goal": {k: str(v) for k, v in goal.items() if k != "last_plan"}, "annual_rate": annual_rate},
                             res, formula_steps=ev.formula_steps, assumptions=ev.assumptions + ["Feasibility compares the requirement to the 6-month average surplus."],
                             missing=ev.missing_inputs + ([] if surplus is not None or snap is None else ["recent cash-flow history"]),
                             source_type="pnc_demo_data")
    return {"plan": res, "evidence": evidence.model_dump(mode="json")}


def _row(r) -> dict:
    d = dict(r)
    for k in ("goal_id",):
        d[k] = str(d[k])
    return d


def create(conn: Connection, customer_id: str, g: GoalIn, as_of: date) -> dict:
    gid = conn.execute(text(
        "INSERT INTO pnc_savings_goals(customer_id, name, target_amount, starting_amount, current_amount, deadline, "
        "planned_monthly_contribution, constraints) VALUES (:c,:n,:t,:s,:s,:d,:p,CAST(:k AS jsonb)) RETURNING goal_id"),
        {"c": customer_id, "n": g.name, "t": g.target_amount, "s": g.starting_amount, "d": g.deadline,
         "p": g.planned_monthly_contribution, "k": json.dumps({"max_monthly_contribution": str(g.max_monthly_contribution) if g.max_monthly_contribution is not None else None})}).scalar_one()
    return get(conn, str(gid))


def get(conn: Connection, goal_id: str) -> dict | None:
    r = conn.execute(text("SELECT * FROM pnc_savings_goals WHERE goal_id = :g"), {"g": goal_id}).mappings().first()
    return _row(r) if r else None


def list_goals(conn: Connection) -> list[dict]:
    return [_row(r) for r in conn.execute(text("SELECT * FROM pnc_savings_goals ORDER BY created_at")).mappings()]


def update(conn: Connection, goal_id: str, fields: dict) -> dict | None:
    allowed = {"name", "target_amount", "deadline", "planned_monthly_contribution", "current_amount", "status"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return get(conn, goal_id)
    clause = ", ".join(f"{k} = :{k}" for k in sets)
    conn.execute(text(f"UPDATE pnc_savings_goals SET {clause} WHERE goal_id = :g"), {**sets, "g": goal_id})
    return get(conn, goal_id)


def delete(conn: Connection, goal_id: str) -> bool:
    return conn.execute(text("DELETE FROM pnc_savings_goals WHERE goal_id = :g"), {"g": goal_id}).rowcount == 1


def save_plan(conn: Connection, goal_id: str, plan: dict) -> None:
    conn.execute(text("UPDATE pnc_savings_goals SET last_plan = CAST(:p AS jsonb), last_recalculated_at = :t WHERE goal_id = :g"),
                 {"p": json.dumps(plan, default=str), "t": datetime.now(timezone.utc), "g": goal_id})
