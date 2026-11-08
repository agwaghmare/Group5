"""Deterministic finance formulas using Decimal. Every public ``calc_*`` returns an ``Evidence`` object.

Conventions
-----------
* Rates are decimal fractions (0.07 = 7%). ``pct`` helpers convert at the API boundary only.
* Currency results are quantised to cents with ROUND_HALF_UP; ratios to 4 decimal places (fractions, not %).
* Monthly rate = annual nominal rate / 12 (APR convention). APY is computed separately.
* Missing/invalid inputs never raise from ``calc_*``: the result is ``None`` and ``missing_inputs`` says why.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, getcontext
from typing import Sequence

from .evidence import Evidence, make_evidence

getcontext().prec = 40
D = Decimal
CENT = D("0.01")
RATIO = D("0.0001")
ZERO = D(0)
SOURCE = "caller_supplied"


def dec(x) -> Decimal:
    return x if isinstance(x, Decimal) else D(str(x))


def money(x: Decimal) -> Decimal:
    return dec(x).quantize(CENT, rounding=ROUND_HALF_UP)


def ratio(x: Decimal) -> Decimal:
    return dec(x).quantize(RATIO, rounding=ROUND_HALF_UP)


def pct_to_rate(pct) -> Decimal:
    """Percent (7.5) -> decimal fraction (0.075)."""
    return dec(pct) / D(100)


def rate_to_pct(rate) -> Decimal:
    return dec(rate) * D(100)


# ------------------------------------------------------------------ primitives (reused by features/policy)
def payment(principal, annual_rate, n_months: int) -> Decimal:
    """Level monthly payment. Zero rate -> principal / n."""
    p, r = dec(principal), dec(annual_rate) / D(12)
    if n_months <= 0:
        raise ValueError("n_months must be positive")
    if r == 0:
        return p / D(n_months)
    return p * r / (D(1) - (D(1) + r) ** (-n_months))


def principal_from_payment(pay, annual_rate, n_months: int) -> Decimal:
    """Inverse of ``payment``: the largest principal a payment supports (amortisation inverse)."""
    pm, r = dec(pay), dec(annual_rate) / D(12)
    if r == 0:
        return pm * D(n_months)
    return pm * (D(1) - (D(1) + r) ** (-n_months)) / r


@dataclass(frozen=True)
class AmortRow:
    month: int
    payment: Decimal
    interest: Decimal
    principal: Decimal
    balance: Decimal


def amortize(principal, annual_rate, n_months: int, extra_monthly=ZERO, max_months: int = 1200) -> list[AmortRow]:
    bal, r = dec(principal), dec(annual_rate) / D(12)
    pay, extra = payment(bal, annual_rate, n_months), dec(extra_monthly)
    rows: list[AmortRow] = []
    m = 0
    while bal > D("0.000001") and m < max_months:
        m += 1
        interest = bal * r
        due = min(pay + extra, bal + interest)
        princ = due - interest
        bal = bal - princ
        if bal < D("0.000001"):   # fold a sub-micro-cent precision residual into the final payment
            due, princ, bal = due + bal, princ + bal, ZERO
        rows.append(AmortRow(m, due, interest, princ, max(bal, ZERO)))
    return rows


def future_value(balance, monthly_contribution, annual_rate, months: int) -> Decimal:
    b, c, r = dec(balance), dec(monthly_contribution), dec(annual_rate) / D(12)
    if r == 0:
        return b + c * D(months)
    g = (D(1) + r) ** months
    return b * g + c * (g - D(1)) / r


# ------------------------------------------------------------------ evidence-returning calculations
def _missing(**kw) -> list[str]:
    return [k for k, v in kw.items() if v is None]


def calc_net_worth(as_of: date, assets: Sequence, liabilities: Sequence, source: str = SOURCE) -> Evidence:
    a, l = [dec(x) for x in assets], [dec(x) for x in liabilities]
    ta, tl = sum(a, ZERO), sum(l, ZERO)
    return make_evidence("net_worth", as_of, {"assets": a, "liabilities": l},
                         {"total_assets": money(ta), "total_liabilities": money(tl), "net_worth": money(ta - tl)},
                         formula_steps=["total_assets = sum(asset balances)", "total_liabilities = sum(liability balances, positive)",
                                        "net_worth = total_assets - total_liabilities"],
                         assumptions=["Liability balances are stored as positive numbers."], source_type=source,
                         units={"total_assets": "USD", "total_liabilities": "USD", "net_worth": "USD"})


def calc_cash_surplus(as_of: date, income, consumption_spending, debt_payments, source: str = SOURCE) -> Evidence:
    i, c, d = dec(income), dec(consumption_spending), dec(debt_payments)
    return make_evidence("monthly_cash_surplus", as_of, {"income": i, "consumption_spending": c, "debt_payments": d},
                         {"cash_surplus": money(i - c - d)},
                         formula_steps=["cash_surplus = income - consumption_spending - debt_payments"],
                         assumptions=["Internal transfers, external cash-management flows and non-cash postings are excluded."],
                         source_type=source, units={"cash_surplus": "USD/month"})


def calc_dti(as_of: date, monthly_debt_payments, gross_monthly_income, source: str = SOURCE) -> Evidence:
    miss = _missing(monthly_debt_payments=monthly_debt_payments, gross_monthly_income=gross_monthly_income)
    if not miss and dec(gross_monthly_income) <= 0:
        miss = ["gross_monthly_income (must be > 0)"]
    res = None
    if not miss:
        res = ratio(dec(monthly_debt_payments) / dec(gross_monthly_income))
    return make_evidence("debt_to_income", as_of, {"monthly_debt_payments": monthly_debt_payments,
                                                   "gross_monthly_income": gross_monthly_income},
                         {"dti": res}, formula_steps=["dti = monthly_debt_payments / gross_monthly_income (fraction)"],
                         missing=miss, source_type=source, units={"dti": "fraction (0.36 = 36%)"})


def calc_utilization(as_of: date, balance, limit, source: str = SOURCE) -> Evidence:
    miss = _missing(balance=balance, limit=limit)
    if not miss and dec(limit) <= 0:
        miss = ["limit (must be > 0)"]
    res = None if miss else ratio(dec(balance) / dec(limit))
    return make_evidence("credit_utilization", as_of, {"balance": balance, "limit": limit}, {"utilization": res},
                         formula_steps=["utilization = revolving_balance / credit_limit (fraction)"], missing=miss,
                         source_type=source, units={"utilization": "fraction"})


def calc_loan_payment(as_of: date, principal, annual_rate, n_months: int, source: str = SOURCE) -> Evidence:
    p, r = dec(principal), dec(annual_rate)
    pay = payment(p, r, n_months)
    return make_evidence("loan_payment", as_of, {"principal": p, "annual_rate": r, "n_months": n_months},
                         {"monthly_payment": money(pay), "total_paid": money(pay * n_months),
                          "total_interest": money(pay * n_months - p)},
                         formula_steps=["r = annual_rate / 12", "payment = P * r / (1 - (1 + r)^-n)  (r = 0: P / n)"],
                         intermediates={"monthly_rate": r / D(12)}, source_type=source, units={"monthly_payment": "USD/month"})


def calc_emergency_months(as_of: date, liquid_savings, essential_monthly_expenses, source: str = SOURCE) -> Evidence:
    miss = _missing(liquid_savings=liquid_savings, essential_monthly_expenses=essential_monthly_expenses)
    if not miss and dec(essential_monthly_expenses) <= 0:
        miss = ["essential_monthly_expenses (must be > 0)"]
    res = None if miss else ratio(dec(liquid_savings) / dec(essential_monthly_expenses))
    return make_evidence("emergency_fund_months", as_of, {"liquid_savings": liquid_savings,
                                                           "essential_monthly_expenses": essential_monthly_expenses},
                         {"months": res}, formula_steps=["months = liquid_savings / essential_monthly_expenses"],
                         missing=miss, source_type=source, units={"months": "months of essential spending"})


def calc_amortization(as_of: date, principal, annual_rate, n_months: int, extra_monthly=ZERO, source: str = SOURCE) -> Evidence:
    base = amortize(principal, annual_rate, n_months)
    ext = amortize(principal, annual_rate, n_months, extra_monthly)
    bi, ei = sum((r.interest for r in base), ZERO), sum((r.interest for r in ext), ZERO)
    return make_evidence(
        "amortization", as_of, {"principal": principal, "annual_rate": annual_rate, "n_months": n_months,
                                "extra_monthly": extra_monthly},
        {"monthly_payment": money(payment(principal, annual_rate, n_months)), "months_to_payoff": len(ext),
         "total_interest": money(ei), "baseline_months": len(base), "baseline_total_interest": money(bi),
         "months_saved": len(base) - len(ext), "interest_saved": money(bi - ei),
         "schedule": [{"month": r.month, "payment": money(r.payment), "interest": money(r.interest),
                       "principal": money(r.principal), "balance": money(r.balance)} for r in ext]},
        formula_steps=["interest_m = balance_{m-1} * annual_rate/12", "principal_m = payment + extra - interest_m",
                       "balance_m = balance_{m-1} - principal_m"],
        assumptions=["Extra principal is applied every month with the scheduled payment; no prepayment penalty."],
        source_type=source)


def calc_apy(as_of: date, nominal_rate, compounds_per_year: int = 12, source: str = SOURCE) -> Evidence:
    r, m = dec(nominal_rate), compounds_per_year
    return make_evidence("apy", as_of, {"nominal_rate": r, "compounds_per_year": m},
                         {"apy": ratio((D(1) + r / D(m)) ** m - D(1))},
                         formula_steps=["apy = (1 + r/m)^m - 1"], source_type=source, units={"apy": "fraction"})


def calc_savings_growth(as_of: date, balance, monthly_contribution, annual_rate, months: int, source: str = SOURCE) -> Evidence:
    fv = future_value(balance, monthly_contribution, annual_rate, months)
    contributed = dec(balance) + dec(monthly_contribution) * months
    return make_evidence("savings_growth", as_of, {"balance": balance, "monthly_contribution": monthly_contribution,
                                                   "annual_rate": annual_rate, "months": months},
                         {"future_value": money(fv), "total_contributed": money(contributed),
                          "growth": money(fv - contributed)},
                         formula_steps=["FV = B*(1+r)^n + C*((1+r)^n - 1)/r, r = annual_rate/12; r = 0: B + C*n"],
                         assumptions=["Contributions at month end; constant rate; no taxes or fees."], source_type=source)


def calc_retirement_projection(as_of: date, current_balance, monthly_contribution, annual_return, years: int,
                               inflation_rate=ZERO, source: str = SOURCE) -> Evidence:
    n = years * 12
    nominal = future_value(current_balance, monthly_contribution, annual_return, n)
    real = nominal / ((D(1) + dec(inflation_rate)) ** years)
    return make_evidence("retirement_projection", as_of,
                         {"current_balance": current_balance, "monthly_contribution": monthly_contribution,
                          "annual_return": annual_return, "years": years, "inflation_rate": inflation_rate},
                         {"nominal_balance": money(nominal), "real_balance_today_dollars": money(real)},
                         formula_steps=["nominal = FV(balance, contribution, return/12, years*12)",
                                        "real = nominal / (1 + inflation)^years"],
                         assumptions=["Constant return and inflation. A projection, not a forecast or guarantee."],
                         limitations=["Does not model market volatility, taxes, or contribution limits."], source_type=source)


@dataclass
class Debt:
    name: str
    balance: Decimal
    apr: Decimal          # decimal fraction
    min_payment: Decimal


def simulate_payoff(debts: Sequence[Debt], extra_monthly, strategy: str, max_months: int = 600) -> dict:
    """Snowball (smallest balance first) or avalanche (highest APR first). Freed minimums roll over."""
    if strategy not in ("snowball", "avalanche"):
        raise ValueError("strategy must be 'snowball' or 'avalanche'")
    live = [Debt(d.name, dec(d.balance), dec(d.apr), dec(d.min_payment)) for d in debts if dec(d.balance) > 0]
    budget = sum((d.min_payment for d in live), ZERO) + dec(extra_monthly)
    total_interest, month, order = ZERO, 0, []
    while live and month < max_months:
        month += 1
        for d in live:
            i = d.balance * d.apr / D(12)
            d.balance += i
            total_interest += i
        key = (lambda d: d.balance) if strategy == "snowball" else (lambda d: -d.apr)
        live.sort(key=key)
        remaining = budget
        for d in live:  # minimums first
            pay = min(d.min_payment, d.balance, remaining)
            d.balance -= pay
            remaining -= pay
        for d in live:  # then everything left to the target debt
            if remaining <= 0:
                break
            pay = min(d.balance, remaining)
            d.balance -= pay
            remaining -= pay
        for d in [x for x in live if x.balance <= D("0.005")]:
            order.append({"debt": d.name, "paid_off_month": month})
        live = [d for d in live if d.balance > D("0.005")]
    return {"months": month, "total_interest": money(total_interest), "payoff_order": order, "converged": not live}


def calc_debt_payoff_compare(as_of: date, debts: Sequence[Debt], extra_monthly, source: str = SOURCE) -> Evidence:
    snow = simulate_payoff(debts, extra_monthly, "snowball")
    aval = simulate_payoff(debts, extra_monthly, "avalanche")
    return make_evidence("debt_payoff_compare", as_of,
                         {"debts": [{"name": d.name, "balance": d.balance, "apr": d.apr, "min_payment": d.min_payment} for d in debts],
                          "extra_monthly": extra_monthly},
                         {"snowball": snow, "avalanche": aval,
                          "interest_difference": money(snow["total_interest"] - aval["total_interest"]),
                          "months_difference": snow["months"] - aval["months"]},
                         formula_steps=["Monthly: accrue interest, pay all minimums, send surplus to target debt.",
                                        "Snowball target = smallest balance; avalanche target = highest APR."],
                         assumptions=["Total monthly budget (sum of minimums + extra) stays constant as debts are paid off."],
                         limitations=["Ignores new borrowing, fees and variable rates."], source_type=source)


def calc_stress_test(as_of: date, liquid_savings, monthly_income, monthly_essential, monthly_debt_payments,
                     income_drop_pct, expense_increase_pct, one_time_shock=ZERO, source: str = SOURCE) -> Evidence:
    inc = dec(monthly_income) * (D(1) - dec(income_drop_pct))
    ess = dec(monthly_essential) * (D(1) + dec(expense_increase_pct))
    burn = ess + dec(monthly_debt_payments) - inc
    start = dec(liquid_savings) - dec(one_time_shock)
    if burn <= 0:
        runway = None
        status = "self_funding"
    elif start <= 0:
        runway, status = ZERO, "shortfall_immediately"
    else:
        runway, status = ratio(start / burn), "drawdown"
    return make_evidence(
        "stress_test", as_of,
        {"liquid_savings": liquid_savings, "monthly_income": monthly_income, "monthly_essential": monthly_essential,
         "monthly_debt_payments": monthly_debt_payments, "income_drop_pct": income_drop_pct,
         "expense_increase_pct": expense_increase_pct, "one_time_shock": one_time_shock},
        {"stressed_income": money(inc), "stressed_essential": money(ess), "monthly_burn": money(burn),
         "starting_liquidity": money(start), "runway_months": runway, "status": status},
        formula_steps=["stressed_income = income*(1-drop)", "stressed_essential = essential*(1+increase)",
                       "burn = stressed_essential + debt_payments - stressed_income",
                       "runway = (liquid - shock) / burn if burn > 0"],
        assumptions=["Discretionary spending is cut to zero in the stress; no new borrowing or assistance."],
        source_type=source, units={"runway_months": "months"})


def calc_npv(as_of: date, annual_discount_rate, cash_flows: Sequence, source: str = SOURCE) -> Evidence:
    r = dec(annual_discount_rate) / D(12)
    flows = [dec(c) for c in cash_flows]
    total = sum((c / ((D(1) + r) ** t) for t, c in enumerate(flows)), ZERO)
    return make_evidence("npv", as_of, {"annual_discount_rate": annual_discount_rate, "cash_flows": flows},
                         {"npv": money(total)}, formula_steps=["npv = sum(CF_t / (1 + rate/12)^t), t = 0 is today"],
                         assumptions=["Monthly periods; t=0 cash flow is not discounted."], source_type=source)


def calc_goal_contribution(as_of: date, target, current, months: int, annual_rate=ZERO, source: str = SOURCE) -> Evidence:
    t, c, r = dec(target), dec(current), dec(annual_rate) / D(12)
    if months <= 0:
        return make_evidence("goal_contribution", as_of, {"target": t, "current": c, "months": months},
                             {"required_monthly": None}, missing=["months (must be > 0)"])
    if r == 0:
        need = (t - c) / D(months)
    else:
        g = (D(1) + r) ** months
        need = (t - c * g) * r / (g - D(1))
    need = max(need, ZERO)
    return make_evidence("goal_contribution", as_of, {"target": t, "current": c, "months": months, "annual_rate": annual_rate},
                         {"required_monthly": money(need), "already_funded": c >= t},
                         formula_steps=["r = 0: (target - current) / n", "else: (target - current*(1+r)^n) * r / ((1+r)^n - 1)"],
                         assumptions=["Contributions at month end; constant rate."], source_type=source,
                         units={"required_monthly": "USD/month"})


def calc_purchase_scenario(as_of: date, price, down_payment, apr, term_months: int, source: str = SOURCE) -> Evidence:
    """Generic financed-purchase affordability maths (used by FutureYou's what-if)."""
    price, down = dec(price), dec(down_payment)
    financed = max(price - down, ZERO)
    pay = payment(financed, dec(apr), term_months) if financed > 0 else ZERO
    return make_evidence("purchase_scenario", as_of, {"price": price, "down_payment": down, "apr": apr, "term_months": term_months},
                         {"financed_amount": money(financed), "monthly_payment": money(pay),
                          "total_interest": money(pay * term_months - financed), "total_cost": money(pay * term_months + down)},
                         formula_steps=["financed = price - down", "payment = loan_payment(financed, apr, term)"],
                         assumptions=["Hypothetical; excludes taxes, fees, insurance and registration."], source_type=source)
