"""Deterministic portfolio math. Synthetic histories are never actual returns."""
import calendar
import hashlib
import json
import math
import random
from datetime import date
from decimal import Decimal

import numpy as np
from fastapi import HTTPException
from sqlalchemy import func, select

from app.orm.authorization import require_feature
from app.orm.models import (
    Customer,
    FinanceSnapshot,
    InvestmentProfile,
    MarketObservation,
    PortfolioAccount,
    PortfolioAssessment,
    PortfolioAssignment,
    PortfolioHistory,
    PortfolioHolding,
    RebalanceProposal,
    User,
)
from app.staff.store import ident, now

BUCKETS = ("stocks", "bonds", "foreign")
LABELS = {"stocks": "Domestic stocks", "bonds": "Domestic bonds", "foreign": "Foreign-market equities"}
SOURCE = "synthetic-correlated-monthly-v1-seed-20261108"
POLICY = "portfolio-risk-v1"
DISCLAIMER = "Synthetic holdings, questionnaire and market history. Modeled returns, not actual client performance. No brokerage orders are sent."


def manager(store):
    require_feature(store, "staff.portfolio")
    if store.user.role_key != "portfolio_manager":
        store.audit("access_denied", "portfolio_clients", "denied")
        raise HTTPException(403, "Only portfolio risk managers may access client portfolios")


def latest_finance(db, client_id):
    return db.scalar(select(FinanceSnapshot).where(FinanceSnapshot.user_id == client_id)
                     .order_by(FinanceSnapshot.date.desc()).limit(1))


def month_offset(day, offset):
    index = day.year * 12 + day.month - 1 + offset
    year, month = divmod(index, 12)
    return date(year, month + 1, calendar.monthrange(year, month + 1)[1])


def allocate_cents(total, weights):
    """Largest remainder: conserve every cent without a negative last bucket."""
    result = [total * w // 1000000 for w in weights]
    order = sorted(range(3), key=lambda i: (total * weights[i]) % 1000000, reverse=True)
    for i in order[:total - sum(result)]:
        result[i] += 1
    return result


def set_holdings(db, account):
    weights = [getattr(account, k + "_ppm") for k in BUCKETS]
    values = allocate_cents(account.value_cents, weights)
    for bucket, value in zip(BUCKETS, values):
        price = db.scalar(select(MarketObservation.total_return_index).where(MarketObservation.bucket == bucket)
                          .order_by(MarketObservation.date.desc()).limit(1))
        holding = db.get(PortfolioHolding, (account.client_id, bucket))
        if not holding:
            holding = PortfolioHolding(client_id=account.client_id, bucket=bucket, instrument=LABELS[bucket],
                asset_class="bond" if bucket == "bonds" else "stock",
                geography="foreign" if bucket == "foreign" else "domestic", currency="USD")
            db.add(holding)
        holding.value_cents = value
        holding.units = Decimal(value) / 100 / price
    db.flush()


def seed_synthetic(db, client_id=None):
    """Idempotent demo additions only for customers sourced from the synthetic tracker."""
    end = db.scalar(select(func.max(FinanceSnapshot.date)))
    if not end:
        return
    if not db.scalar(select(MarketObservation.bucket).limit(1)):
        rng = random.Random(20261108)
        indices = [100., 100., 100.]
        for period in range(61):
            if period:
                common = rng.gauss(0, 1)
                shock = -.16 if period == 35 else 0
                changes = [.006 + .035 * common + .012 * rng.gauss(0, 1) + shock,
                           .002 + .007 * rng.gauss(0, 1) - .001 * common,
                           .0055 + .037 * common + .022 * rng.gauss(0, 1) + shock + .008 * rng.gauss(0, 1)]
                indices = [v * (1 + r) for v, r in zip(indices, changes)]
            for bucket, value in zip(BUCKETS, indices):
                db.add(MarketObservation(bucket=bucket, date=month_offset(end, period - 60),
                    total_return_index=Decimal(str(value)), source=SOURCE, synthetic=True))
        db.flush()
    eligible = db.scalars(select(Customer).where(Customer.source_type == "synthetic_finance_tracker",
        ~Customer.tracker_id.in_(select(PortfolioAccount.client_id)))).all()
    for customer in eligible:
        if client_id is not None and customer.tracker_id != client_id:
            continue
        f = latest_finance(db, customer.tracker_id)
        if not f or f.portfolio_value is None or f.portfolio_value <= 0:
            continue
        rng = random.Random(20261108 + customer.tracker_id)
        equity = max(0., min(1., float(f.equity_allocation_pct if f.equity_allocation_pct is not None else 50) / 100))
        foreign = round(equity * .25 * 1000000)
        stocks = round(equity * 1000000) - foreign
        account = PortfolioAccount(client_id=customer.tracker_id, stocks_ppm=stocks,
            bonds_ppm=1000000 - stocks - foreign, foreign_ppm=foreign,
            value_cents=round(float(f.portfolio_value) * 100), revision=1, as_of=f.date.isoformat(), synthetic=True)
        db.add(account)
        db.add(InvestmentProfile(client_id=customer.tracker_id, goal="Long-term wealth building (synthetic)",
            horizon_months=rng.choice([24, 60, 120, 240]), tolerance=rng.randint(1, 5),
            liquidity_need_cents=round(float(f.recurring_bill_total or 0) * 100 * 3),
            target_return=Decimal("0.05"), synthetic=True,
            questionnaire={"source": "Synthetic questionnaire; confirm with client", "loss_response": "Review the plan before changing holdings"}))
        db.flush()
        set_holdings(db, account)
        db.add(PortfolioHistory(id="PORT-INIT-" + str(customer.tracker_id), client_id=customer.tracker_id,
            recorded_at=now(), event="synthetic_portfolio_initialized", evidence={
                "allocations": allocation(account), "value_cents": account.value_cents, "data_as_of": account.as_of,
                "source": "Tracker portfolio_value and equity_allocation_pct; foreign split modeled", "synthetic": True}))
    db.flush()


def allocation(account):
    return {k: getattr(account, k + "_ppm") / 1000000 for k in BUCKETS}


def assigned_account(store, client_id):
    manager(store)
    assignment = store.db.get(PortfolioAssignment, client_id)
    if not assignment or assignment.manager_id != store.user.employee_id:
        store.audit("access_denied", "portfolio_client", "denied")
        raise HTTPException(404, "Client is not assigned to your portfolio workspace")
    account = store.db.get(PortfolioAccount, client_id)
    if not account:
        raise HTTPException(404, "Portfolio data is not available")
    return account


def client_queue(store, unassigned=False, search=""):
    manager(store)
    seed_synthetic(store.db)
    query = select(Customer.tracker_id, User.display_name).join(User, User.id == Customer.user_id).join(
        PortfolioAccount, PortfolioAccount.client_id == Customer.tracker_id).outerjoin(
        PortfolioAssignment, PortfolioAssignment.client_id == Customer.tracker_id)
    query = query.where(PortfolioAssignment.client_id.is_(None)) if unassigned else query.where(
        PortfolioAssignment.manager_id == store.user.employee_id)
    if search:
        # Only a client label is searchable before assignment; no finance/holdings disclosure.
        query = query.where(User.display_name.ilike("%" + search.replace("%", "").replace("_", "") + "%"))
    return [{"client_id": cid, "name": name, "synthetic": True} for cid, name in store.db.execute(query.order_by(Customer.tracker_id).limit(200))]


def assign_client(store, client_id):
    manager(store)
    seed_synthetic(store.db)
    if not store.db.get(PortfolioAccount, client_id):
        raise HTTPException(404, "Client has no supported portfolio")
    existing = store.db.get(PortfolioAssignment, client_id)
    if existing:
        if existing.manager_id != store.user.employee_id:
            raise HTTPException(409, "Client is already assigned to another manager")
        return {"client_id": client_id, "assigned": True}
    # Store's BEGIN IMMEDIATE plus the PK serializes competing self-assignment requests.
    store.db.add(PortfolioAssignment(client_id=client_id, manager_id=store.user.employee_id, assigned_at=now()))
    store.db.flush()
    store.audit("portfolio_client_assigned", str(client_id))
    return {"client_id": client_id, "assigned": True}


def market_matrix(db):
    series = [db.scalars(select(MarketObservation).where(MarketObservation.bucket == b)
                        .order_by(MarketObservation.date)).all() for b in BUCKETS]
    if min(map(len, series)) < 25 or any([r.date for r in s] != [r.date for r in series[0]] for s in series):
        raise HTTPException(409, "At least two years of aligned market history are required")
    prices = np.array([[float(r.total_return_index) for r in s] for s in series]).T
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise HTTPException(409, "Market data contains invalid prices")
    return prices[1:] / prices[:-1] - 1, [r.date.isoformat() for r in series[0]], series[0][-1].source


def performance(returns, weights):
    path = np.cumprod(1 + returns @ np.array(weights))
    curve = np.concatenate(([1.], path))
    variance = float(np.array(weights) @ np.cov(returns, rowvar=False, ddof=1) @ np.array(weights))
    return {"annualized_return": round(float(path[-1] ** (12 / len(path)) - 1), 8),
            "total_return": round(float(path[-1] - 1), 8),
            "volatility": round(math.sqrt(max(0, variance) * 12), 8),
            "max_drawdown": round(float(np.min(curve / np.maximum.accumulate(curve) - 1)), 8)}


def suitable_weights(returns, current, risk_budget, goal):
    """Shared read-only preview/proposal search; never changes current holdings."""
    choices = []
    for stocks in range(0, 1000001, 50000):
        for foreign in range(0, 1000001 - stocks, 50000):
            weights = [stocks / 1000000, (1000000 - stocks - foreign) / 1000000, foreign / 1000000]
            metrics = performance(returns, weights)
            if metrics["volatility"] <= risk_budget and max(weights) <= .8:
                choices.append((metrics["annualized_return"], weights))
    meeting = [item for item in choices if item[0] >= goal]
    if meeting:
        return min(meeting, key=lambda item: sum(abs(a-b) for a, b in zip(item[1], current)))[1]
    return max(choices)[1] if choices else None


def assessment(store, account, weights=None, profile_override=None):
    profile = profile_override or store.db.get(InvestmentProfile, account.client_id)
    f = latest_finance(store.db, account.client_id)
    returns, dates, source = market_matrix(store.db)
    a = weights or allocation(account)
    missing = [k for k in ("monthly_income", "minimum_debt_payment", "recurring_bill_total", "emergency_fund_months", "income_volatility_3m")
               if f is None or getattr(f, k) is None]
    income = float(f.monthly_income or 0) if f else 0
    debt_ratio = float(f.minimum_debt_payment or 0) / income if income > 0 else None
    emergency = float(f.emergency_fund_months or 0) if f else 0
    income_vol = float(f.income_volatility_3m or 0) if f else 0
    surplus = income - float(f.recurring_bill_total or 0) - float(f.minimum_debt_payment or 0) if f else 0
    capacity = "low" if emergency < 3 or income <= 0 or surplus <= 0 or debt_ratio is None or debt_ratio > .4 else (
        "moderate" if emergency < 6 or income_vol > .2 or debt_ratio > .25 else "high")
    capacity_limit = {"low": .08, "moderate": .12, "high": .18}[capacity]
    tolerance_limit = {1: .06, 2: .09, 3: .12, 4: .16, 5: .20}[profile.tolerance]
    horizon_limit = .06 if profile.horizon_months < 36 else .12 if profile.horizon_months < 84 else .20
    liquidity_limit = .08 if profile.liquidity_need_cents > account.value_cents * .25 else None
    limits = {"financial_capacity": capacity_limit, "stated_tolerance": tolerance_limit,
              "investment_horizon": horizon_limit, "liquidity_need": liquidity_limit}
    limit = min(value for value in limits.values() if value is not None)
    binding = [name for name, value in limits.items() if value == limit]
    metrics = performance(returns, list(a.values()))
    benchmark = performance(returns, [.45, .40, .15])
    flags = []
    if metrics["volatility"] > limit:
        flags.append("risk_above_budget")
    if max(a.values()) > .8:
        flags.append("concentrated_allocation")
    if metrics["annualized_return"] < float(profile.target_return):
        flags.append("modeled_return_below_goal")
    if missing:
        flags.append("incomplete_financial_profile")
    target = None if missing else suitable_weights(returns, list(a.values()), limit, float(profile.target_return))
    preview = None
    target_path = None
    if target is not None:
        target_metrics = performance(returns, target)
        preview = {"allocations": dict(zip(BUCKETS, target)), "metrics": target_metrics,
                   "goal_feasible": target_metrics["annualized_return"] >= float(profile.target_return),
                   "same_as_current": all(abs(before-after) < .000001 for before, after in zip(a.values(), target)),
                   "requires_approval": True}
        target_path = np.concatenate(([1.], np.cumprod(1 + returns @ np.array(target))))
    modeled = np.concatenate(([1.], np.cumprod(1 + returns @ np.array(list(a.values())))))
    benchmark_path = np.concatenate(([1.], np.cumprod(1 + returns @ np.array([.45, .40, .15]))))
    as_of = dates[-1]
    finance = {"monthly_income": income, "monthly_debt_payment": float(f.minimum_debt_payment or 0) if f else None,
        "recurring_bills": float(f.recurring_bill_total or 0) if f else None, "emergency_fund_months": emergency,
        "income_volatility": income_vol, "debt_payment_to_income": debt_ratio, "monthly_surplus": surplus,
        "finance_as_of": f.date.isoformat() if f else None}
    context = {"finance": finance, "profile": profile_json(profile), "market_as_of": as_of,
               "revision": account.revision, "source": source, "policy": POLICY,
               "market_hash": hashlib.sha256(returns.tobytes()).hexdigest()}
    digest = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
    return {"policy_version": POLICY, "allocations": a, "metrics": metrics, "benchmark": benchmark,
        "risk_capacity": capacity, "stated_tolerance": profile.tolerance, "risk_budget": limit,
        "flags": flags, "missing_inputs": missing, "financial_context": finance,
        "risk_limits": limits, "binding_limits": binding, "profile_model": preview,
        "context_hash": digest, "data_as_of": as_of, "window_start": dates[0], "observations": len(returns),
        "market_source": source, "history_stale": (date.today() - date.fromisoformat(as_of)).days > 90,
        "return_history": [{"date": d, "portfolio_index": round(float(v) * 100, 4),
                            "benchmark_index": round(float(b) * 100, 4),
                            "profile_model_index": round(float(target_path[i]) * 100, 4) if target_path is not None else None}
                           for i, (d, v, b) in enumerate(zip(dates, modeled, benchmark_path))],
        "method": "Monthly constant-mix model; annualized sample covariance; gross of costs. Benchmark: 45% domestic stocks / 40% bonds / 15% foreign equities.",
        "limitations": [DISCLAIMER, "Risk budgets are versioned prototype assumptions, not a validated suitability score.",
                        "Future returns are not predicted. Tax lots, actual trading behavior and currency hedges are unavailable."]}


def profile_json(p):
    return {"goal": p.goal, "horizon_months": p.horizon_months, "tolerance": p.tolerance,
        "liquidity_need_cents": p.liquidity_need_cents, "target_return": float(p.target_return),
        "questionnaire": p.questionnaire, "synthetic": p.synthetic}


def client_detail(store, client_id):
    account = assigned_account(store, client_id)
    customer = store.db.get(Customer, client_id)
    user = store.db.get(User, customer.user_id)
    holdings = store.db.scalars(select(PortfolioHolding).where(PortfolioHolding.client_id == client_id)).all()
    latest = store.db.scalar(select(PortfolioAssessment).where(PortfolioAssessment.client_id == client_id,
        PortfolioAssessment.revision == account.revision).order_by(PortfolioAssessment.assessed_at.desc()).limit(1))
    assessments = store.db.scalars(select(PortfolioAssessment).where(PortfolioAssessment.client_id == client_id)
                                  .order_by(PortfolioAssessment.assessed_at.desc()).limit(50)).all()
    history = store.db.scalars(select(PortfolioHistory).where(PortfolioHistory.client_id == client_id)
                              .order_by(PortfolioHistory.recorded_at.desc()).limit(100)).all()
    proposals = store.db.scalars(select(RebalanceProposal).where(RebalanceProposal.client_id == client_id)
                                .order_by(RebalanceProposal.created_at.desc()).limit(20)).all()
    snapshots = store.db.scalars(select(FinanceSnapshot).where(FinanceSnapshot.user_id == client_id)
                                 .order_by(FinanceSnapshot.date.desc()).limit(120)).all()[::-1]
    store.audit("portfolio_client_read", str(client_id))
    return {"client_id": client_id, "name": user.display_name, "revision": account.revision,
        "value_cents": account.value_cents, "allocations": allocation(account), "as_of": account.as_of,
        "profile": profile_json(store.db.get(InvestmentProfile, client_id)),
        "holdings": [{"bucket": h.bucket, "instrument": h.instrument, "asset_class": h.asset_class,
            "geography": h.geography, "value_cents": h.value_cents, "units": float(h.units), "currency": h.currency} for h in holdings],
        "assessment": latest.evidence if latest else None,
        "assessment_history": [{"id": a.id, "assessed_at": a.assessed_at, "revision": a.revision,
            "metrics": a.evidence["metrics"], "risk_capacity": a.evidence["risk_capacity"],
            "risk_budget": a.evidence["risk_budget"], "allocations": a.evidence["allocations"]} for a in assessments],
        "proposals": [proposal_json(p) for p in proposals],
        "history": [{"id": h.id, "recorded_at": h.recorded_at, "event": h.event, **h.evidence} for h in history],
        "financial_history": [{"date": f.date.isoformat(), "portfolio_value": float(f.portfolio_value) if f.portfolio_value is not None else None,
            "monthly_savings_contribution": float(f.monthly_savings_contribution) if f.monthly_savings_contribution is not None else None,
            "income_volatility": float(f.income_volatility_3m) if f.income_volatility_3m is not None else None,
            "late_payments": f.late_payments_12m} for f in snapshots],
        "behavior": {"source": "Imported monthly finance snapshots", "snapshot_count": len(snapshots),
            "note": "Savings contributions and income patterns are observed in tracker snapshots. Actual buy/sell trades and portfolio deposits/withdrawals are unavailable; no trading behavior is inferred."},
        "disclaimer": DISCLAIMER, "synthetic": True}


def run_assessment(store, client_id):
    account = assigned_account(store, client_id)
    evidence = assessment(store, account)
    row = PortfolioAssessment(id=ident("PA"), client_id=client_id, manager_id=store.user.employee_id,
                             revision=account.revision, assessed_at=now(), evidence=evidence)
    store.db.add(row)
    store.audit("portfolio_assessed", str(client_id), assessment_id=row.id)
    store.db.flush()
    return evidence


def assistant_evidence(store, client_id):
    account = assigned_account(store, client_id)
    evidence = assessment(store, account)
    # The chat needs the calculated summary, not every chart point or identity.
    evidence.pop("return_history", None)
    evidence.pop("context_hash", None)
    evidence["investment_profile"] = profile_json(store.db.get(InvestmentProfile, client_id))
    proposal = store.db.scalar(select(RebalanceProposal).where(
        RebalanceProposal.client_id == client_id, RebalanceProposal.manager_id == store.user.employee_id,
        RebalanceProposal.base_revision == account.revision, RebalanceProposal.status == "proposed")
        .order_by(RebalanceProposal.created_at.desc()).limit(1))
    if proposal:
        evidence["pending_proposal"] = {"allocations": proposal.evidence["after"]["allocations"],
            "metrics": proposal.evidence["after"]["metrics"], "estimated_cost_cents": proposal.evidence["estimated_cost_cents"],
            "approval_allowed": proposal.evidence.get("approval_allowed", False),
            "constraint_violations": proposal.evidence.get("constraint_violations", []),
            "rationale": proposal.evidence["rationale"], "requires_human_approval": True}
    return evidence


def update_profile(store, client_id, body):
    account = assigned_account(store, client_id)
    p = store.db.get(InvestmentProfile, client_id)
    with store.db.begin_nested():
        for key in ("goal", "horizon_months", "tolerance", "liquidity_need_cents", "target_return"):
            setattr(p, key, getattr(body, key))
        p.synthetic = True  # A manager edit is a prototype assumption, not a client attestation.
        p.questionnaire = {"source": "Manager-entered prototype assumptions; confirm with client", "updated_at": now()}
        account.revision += 1
        store.db.add(PortfolioHistory(id=ident("PH"), client_id=client_id, recorded_at=now(),
            event="investment_profile_updated", evidence={"profile": profile_json(p), "revision": account.revision}))
        store.audit("portfolio_profile_updated", str(client_id))
        store.db.flush()
        fresh = run_assessment(store, client_id)
        result = {**profile_json(p), "assessment": fresh, "revision": account.revision, "saved": True}
    return result


def proposal_json(p):
    return {"id": p.id, "status": p.status, "base_revision": p.base_revision, "created_at": p.created_at,
            "approved_at": p.approved_at, **p.evidence}


def allocation_violations(summary):
    violations = []
    if summary["metrics"]["volatility"] > summary["risk_budget"] + 1e-8:
        violations.append({"code": "risk_budget", "message": "Portfolio volatility exceeds the client's risk budget",
                           "actual": summary["metrics"]["volatility"], "limit": summary["risk_budget"]})
    concentration = max(summary["allocations"].values())
    if concentration > .8:
        violations.append({"code": "concentration", "message": "A single allocation bucket exceeds the concentration limit",
                           "actual": concentration, "limit": .8})
    return violations


def propose(store, client_id, requested, rationale):
    account = assigned_account(store, client_id)
    before = assessment(store, account)
    if before["missing_inputs"]:
        raise HTTPException(409, "Complete the client's financial profile before proposing a rebalance")
    returns, _, _ = market_matrix(store.db)
    if requested is None:
        weights = suitable_weights(returns, list(allocation(account).values()), before["risk_budget"],
                                   float(store.db.get(InvestmentProfile, client_id).target_return))
        if weights is None:
            raise HTTPException(409, "No supported allocation meets this risk budget; review goals and constraints")
        requested = dict(zip(BUCKETS, weights))
    ppm = {k: int(Decimal(str(requested[k])) * 1000000) for k in BUCKETS}
    after = assessment(store, account, {k: ppm[k] / 1000000 for k in BUCKETS})
    violations = allocation_violations(after)
    no_change = all(ppm[k] == getattr(account, k + "_ppm") for k in BUCKETS)
    values = allocate_cents(account.value_cents, list(ppm.values()))
    existing = allocate_cents(account.value_cents, [getattr(account, k + "_ppm") for k in BUCKETS])
    trades = [{"bucket": k, "delta_cents": new-old} for k, new, old in zip(BUCKETS, values, existing)]
    turnover = sum(abs(t["delta_cents"]) for t in trades) / 2
    cost = math.ceil(turnover * .001)  # Explicit synthetic 10bps one-way turnover assumption.
    row = RebalanceProposal(id=ident("RP"), client_id=client_id, manager_id=store.user.employee_id,
        base_revision=account.revision, **{k + "_ppm": v for k, v in ppm.items()}, status="proposed", created_at=now(),
        evidence={"before": before, "after": after, "trades": trades, "estimated_cost_cents": cost,
            "cost_assumption": "Synthetic 0.10% of one-way turnover; excludes taxes", "rationale": rationale,
            "goal_feasible": after["metrics"]["annualized_return"] >= float(store.db.get(InvestmentProfile, client_id).target_return),
            "no_change": no_change, "approval_allowed": not violations and not no_change,
            "constraint_violations": violations,
            "simulated": True, "sent_externally": False})
    store.db.add(row)
    store.db.flush()
    store.audit("portfolio_rebalance_proposed", str(client_id), proposal_id=row.id)
    return proposal_json(row)


def approve(store, client_id, proposal_id, rationale):
    account = assigned_account(store, client_id)
    p = store.db.get(RebalanceProposal, proposal_id)
    if not p or p.client_id != client_id or p.manager_id != store.user.employee_id:
        raise HTTPException(404, "Proposal not found in your workspace")
    if p.status == "approved":
        return {"approved": True, "revision": account.revision, "simulated": True}
    current = assessment(store, account)
    if p.base_revision != account.revision or current["context_hash"] != p.evidence["before"]["context_hash"]:
        raise HTTPException(409, "Portfolio or financial context changed; generate a new proposal")
    if all(getattr(p, k + "_ppm") == getattr(account, k + "_ppm") for k in BUCKETS):
        raise HTTPException(409, "No allocation change: no rebalance or approval is needed")
    proposed = assessment(store, account, {k: getattr(p, k + "_ppm") / 1000000 for k in BUCKETS})
    violations = allocation_violations(proposed)
    if violations:
        store.audit("portfolio_rebalance_blocked", str(client_id), "denied", proposal_id=p.id,
                    constraint_codes=[v["code"] for v in violations])
        raise HTTPException(422, "This preview cannot be approved: risk budget or concentration limit exceeded")
    for k in BUCKETS:
        setattr(account, k + "_ppm", getattr(p, k + "_ppm"))
    account.value_cents -= p.evidence["estimated_cost_cents"]
    account.revision += 1
    account.as_of = current["data_as_of"]
    p.status, p.approved_at = "approved", now()
    set_holdings(store.db, account)
    store.db.add(PortfolioHistory(id=ident("PH"), client_id=client_id, recorded_at=now(),
        event="simulated_rebalance_approved", evidence={"proposal_id": p.id, "allocations": allocation(account),
            "value_cents": account.value_cents, "revision": account.revision, "rationale": rationale,
            "estimated_cost_cents": p.evidence["estimated_cost_cents"], "sent_externally": False}))
    store.audit("portfolio_rebalance_approved", str(client_id), proposal_id=p.id, simulated=True)
    store.db.flush()
    run_assessment(store, client_id)
    return {"approved": True, "revision": account.revision, "simulated": True}


ACTIVITY_LABELS = {
    "portfolio_client_assigned": "Client assigned",
    "portfolio_assessed": "Risk assessment saved",
    "portfolio_profile_updated": "Investment profile updated",
    "portfolio_rebalance_proposed": "Rebalance preview saved",
    "portfolio_rebalance_approved": "Simulated rebalance approved",
    "portfolio_rebalance_blocked": "Rebalance approval blocked",
}


def activity(store, action="", limit=100):
    """This manager's portfolio actions only, still restricted to assigned clients."""
    from sqlalchemy import String, cast

    from app.orm.models import AuditLog
    manager(store)
    if action and action not in ACTIVITY_LABELS:
        raise HTTPException(422, "Choose a supported portfolio activity type")
    clients = select(cast(PortfolioAssignment.client_id, String)).where(
        PortfolioAssignment.manager_id == store.user.employee_id)
    query = select(AuditLog).where(AuditLog.payload["actor"].as_string() == store.user.id,
        AuditLog.payload["resource"].as_string().in_(clients),
        AuditLog.payload["action"].as_string().in_([action] if action else list(ACTIVITY_LABELS)))
    rows = store.db.scalars(query.order_by(AuditLog.payload["ts"].as_string().desc(), AuditLog.id.desc()).limit(limit)).all()
    names = dict(store.db.execute(select(Customer.tracker_id, User.display_name).join(User, Customer.user_id == User.id)
        .join(PortfolioAssignment, PortfolioAssignment.client_id == Customer.tracker_id)
        .where(PortfolioAssignment.manager_id == store.user.employee_id)).all())
    events = []
    for row in rows:
        e = row.payload
        cid = int(e["resource"])
        fields = [{"label": "Client", "value": str(cid)}, {"label": "Result", "value": e["outcome"]}]
        note = "Recorded in your assigned-client workspace."
        if e.get("assessment_id"):
            a = store.db.get(PortfolioAssessment, e["assessment_id"])
            if a and a.client_id == cid and a.manager_id == store.user.employee_id:
                note = f"Risk capacity: {a.evidence['risk_capacity']}. Portfolio revision {a.revision}."
                fields += [{"label": "Volatility", "value": f"{a.evidence['metrics']['volatility'] * 100:.2f}%"},
                           {"label": "Risk budget", "value": f"{a.evidence['risk_budget'] * 100:.2f}%"}]
        if e.get("proposal_id"):
            p = store.db.get(RebalanceProposal, e["proposal_id"])
            if p and p.client_id == cid and p.manager_id == store.user.employee_id:
                note = p.evidence["rationale"]
                fields += [{"label": "Proposed allocation", "value": " / ".join(
                    f"{LABELS[k]} {p.evidence['after']['allocations'][k] * 100:.2f}%" for k in BUCKETS)},
                    {"label": "Estimated cost", "value": f"${p.evidence['estimated_cost_cents'] / 100:,.2f}"},
                    {"label": "Execution", "value": "Simulated; no orders sent"}]
                if e["action"] == "portfolio_rebalance_proposed":
                    fields.append({"label": "Preview only", "value": "Approval is a separate human action"})
        if e["action"] == "portfolio_profile_updated":
            saved = store.db.scalar(select(PortfolioHistory).where(PortfolioHistory.client_id == cid,
                PortfolioHistory.event == "investment_profile_updated", PortfolioHistory.recorded_at <= e["ts"])
                .order_by(PortfolioHistory.recorded_at.desc()).limit(1))
            if saved:
                profile = saved.evidence["profile"]
                note = profile["goal"]
                fields += [{"label": "Stated tolerance", "value": f"{profile['tolerance']} / 5"},
                           {"label": "Investment horizon", "value": f"{profile['horizon_months']} months"}]
        events.append({"id": row.id, "action": e["action"], "title": ACTIVITY_LABELS[e["action"]],
            "client_id": cid, "client_name": names[cid], "when": e["ts"], "outcome": e["outcome"],
            "detail": note, "fields": fields})
    store.audit("portfolio_activity_read")
    return {"events": events, "limit": limit, "scope": "own_actions_on_assigned_clients", "simulated": True}


def portfolio_summary(store):
    """Own book workflow counts; suppress risk/return means below five contributors."""
    manager(store)
    accounts = store.db.scalars(select(PortfolioAccount).join(PortfolioAssignment,
        PortfolioAssignment.client_id == PortfolioAccount.client_id).where(
        PortfolioAssignment.manager_id == store.user.employee_id)).all()
    assessed = []
    pending_clients = 0
    for account in accounts:
        latest = store.db.scalar(select(PortfolioAssessment).where(
            PortfolioAssessment.client_id == account.client_id, PortfolioAssessment.revision == account.revision)
            .order_by(PortfolioAssessment.assessed_at.desc()).limit(1))
        if latest:
            assessed.append(latest.evidence)
        pending = store.db.scalar(select(RebalanceProposal.id).where(
            RebalanceProposal.client_id == account.client_id,
            RebalanceProposal.manager_id == store.user.employee_id,
            RebalanceProposal.base_revision == account.revision,
            RebalanceProposal.status == "proposed").limit(1))
        pending_clients += int(pending is not None)
    n = len(assessed)
    store.audit("portfolio_summary_read")
    return {"scope": "assigned_clients_only", "assigned_clients": len(accounts),
        "assessed_clients": n, "needs_assessment": len(accounts) - n,
        "above_risk_budget": sum("risk_above_budget" in e["flags"] for e in assessed),
        "within_risk_budget": sum("risk_above_budget" not in e["flags"] for e in assessed),
        "clients_with_pending_previews": pending_clients,
        "mean_volatility": round(sum(e["metrics"]["volatility"] for e in assessed) / n, 8) if n >= 5 else None,
        "mean_annualized_return": round(sum(e["metrics"]["annualized_return"] for e in assessed) / n, 8) if n >= 5 else None,
        "suppression_threshold": 5, "aggregate_contributors": n,
        "aggregate_note": "Risk and return averages require five current assessments, not just five assigned clients. Workflow counts cover only your authorized client list.",
        "method": "Equal-weighted means of latest saved assessments for current portfolio revisions; synthetic historical modeled performance."}
