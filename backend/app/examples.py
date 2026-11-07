"""Turn a lesson example spec into a worked numerical walkthrough."""

from __future__ import annotations

from app.finance_math import (
    amortize,
    annuity_future_value,
    apy_from_nominal,
    expected_value,
    future_value,
    lease_parts,
    log_return,
    modified_duration_price_change,
    money,
    money_factor_to_apr,
    payment,
    pct,
    present_value,
    simple_return,
)


def render_example(spec: dict) -> dict:
    kind = spec["kind"]
    renderer = RENDERERS[kind]
    steps, result, computed = renderer(spec)
    return {
        "title": spec["title"],
        "kind": kind,
        "inputs": {k: v for k, v in spec.items() if k not in {"title", "kind"}},
        "steps": steps,
        "result": result,
        "computed": computed,
    }


def _loan(spec: dict) -> tuple[list[str], str, dict]:
    principal = float(spec["principal"])
    apr = float(spec["apr"])
    months = int(spec["months"])
    extra = float(spec.get("extra", 0))
    base = amortize(principal, apr, months, extra=0)
    with_extra = amortize(principal, apr, months, extra=extra) if extra else base
    steps = [
        f"Amount borrowed P = {money(principal)}, APR = {pct(apr)}, term n = {months} months.",
        "Monthly rate r = APR / 12.",
        "Payment M = P × r × (1 + r)^n / ((1 + r)^n − 1).",
        f"That payment is {money(base.payment)}.",
        (
            f"Month 1 interest = {money(base.first_interest)}. "
            f"Month 1 principal = {money(base.first_principal)}. "
            f"Balance afterward = {money(base.balance_after_first)}."
        ),
        (
            f"If you pay exactly the scheduled amount, total interest is {money(base.total_interest)} "
            f"over {base.months} months."
        ),
    ]
    result = f"Scheduled payment {money(base.payment)}; total interest {money(base.total_interest)}."
    computed = {
        "payment": round(base.payment, 2),
        "total_interest": round(base.total_interest, 2),
        "first_interest": round(base.first_interest, 2),
        "first_principal": round(base.first_principal, 2),
    }
    if extra:
        saved = base.total_interest - with_extra.total_interest
        steps.append(
            f"Adding {money(extra)} extra principal each month finishes in {with_extra.months} months "
            f"and cuts interest by {money(saved)}."
        )
        result = (
            f"Extra {money(extra)}/month saves {money(saved)} of interest "
            f"and {base.months - with_extra.months} months."
        )
        computed["interest_saved"] = round(saved, 2)
        computed["months_saved"] = base.months - with_extra.months
    return steps, result, computed


def _apy(spec: dict) -> tuple[list[str], str, dict]:
    nominal = float(spec["nominal_apr"])
    n = int(spec["compounds"])
    deposit = float(spec.get("deposit", 10000))
    apy = apy_from_nominal(nominal, n) * 100.0
    grown = future_value(deposit, apy, 1)
    steps = [
        f"Nominal rate = {pct(nominal)}, compounded {n} times a year.",
        "APY = (1 + nominal/n)^n − 1.",
        f"APY = {pct(apy, 3)}.",
        f"A {money(deposit)} deposit grows to {money(grown)} after one year at that APY, with no added deposits.",
    ]
    return steps, f"APY is {pct(apy, 3)}; one-year balance {money(grown)}.", {"apy": round(apy, 4), "balance": round(grown, 2)}


def _cd(spec: dict) -> tuple[list[str], str, dict]:
    principal = float(spec["principal"])
    apy = float(spec["apy"])
    years = float(spec["years"])
    value = future_value(principal, apy, years)
    interest = value - principal
    steps = [
        f"CD principal = {money(principal)}, APY = {pct(apy)}, term = {years:g} years.",
        "Future value = principal × (1 + APY)^years. APY is already the effective annual yield.",
        f"Value at maturity = {money(value)}, of which {money(interest)} is interest.",
        "Taking the money out early can trigger a penalty, so this result assumes you hold the CD to maturity.",
    ]
    return steps, f"Maturity value {money(value)}.", {"maturity": round(value, 2), "interest": round(interest, 2)}


def _ira(spec: dict) -> tuple[list[str], str, dict]:
    contribution = float(spec["annual_contribution"])
    rate = float(spec["annual_return"])
    years = int(spec["years"])
    fv = annuity_future_value(contribution, rate, years)
    contributed = contribution * years
    steps = [
        f"Contribute {money(contribution)} at the end of each year for {years} years.",
        f"Assume a constant effective annual return of {pct(rate)}. Real markets do not return a constant rate.",
        "Future value = contribution × ((1 + r)^years − 1) / r, with r = return as a decimal.",
        f"You would have contributed {money(contributed)} and the account would be worth about {money(fv)}.",
        "Traditional and Roth IRAs change when the tax is paid. This example ignores taxes so the growth math stays visible.",
    ]
    return steps, f"Projected balance {money(fv)} before taxes.", {"future_value": round(fv, 2)}


def _utilization(spec: dict) -> tuple[list[str], str, dict]:
    balance = float(spec["balance"])
    limit = float(spec["limit"])
    ratio = balance / limit if limit else 0.0
    steps = [
        f"Card balances = {money(balance)}. Credit limits = {money(limit)}.",
        "Utilization = balances / limits.",
        f"Utilization = {ratio:.1%}.",
        "A common coaching range is to keep reported utilization under about 30%. It is a guideline, not a rule in the scoring formula you can see.",
    ]
    return steps, f"Utilization is {ratio:.1%}.", {"utilization": round(ratio, 4)}


def _depreciation(spec: dict) -> tuple[list[str], str, dict]:
    price = float(spec["price"])
    market = float(spec["market"])
    months = int(spec["months_owned"])
    drop = price - market
    per_year = drop / months * 12 if months else 0.0
    steps = [
        f"Price when the contract started = {money(price)}. Estimated market value now = {money(market)}.",
        "Depreciation = starting price − current market value.",
        f"The vehicle has depreciated about {money(drop)} over {months} months, roughly {money(per_year)} per year.",
        "Market value is an estimate. A dealer appraisal is what a trade-in actually uses.",
    ]
    return steps, f"Depreciation to date {money(drop)}.", {"depreciation": round(drop, 2)}


def _lease(spec: dict) -> tuple[list[str], str, dict]:
    cap = float(spec["cap"])
    residual = float(spec["residual"])
    term = int(spec["term"])
    factor = float(spec["money_factor"])
    dep, rent, pay = lease_parts(cap, residual, term, factor)
    apr = money_factor_to_apr(factor)
    steps = [
        f"Capitalized cost = {money(cap)}, residual = {money(residual)}, term = {term} months, money factor = {factor:.5f}.",
        "Depreciation portion = (cap − residual) / term.",
        "Rent charge = (cap + residual) × money factor.",
        f"Depreciation portion = {money(dep)}. Rent charge = {money(rent)}. Base payment ≈ {money(pay)}.",
        f"A money factor converts approximately as APR ≈ factor × 2400 = {pct(apr)}.",
    ]
    return steps, f"Base payment about {money(pay)} before taxes.", {"payment": round(pay, 2), "apr_approx": round(apr, 2)}


def _tvm(spec: dict) -> tuple[list[str], str, dict]:
    pv = float(spec["present"])
    rate = float(spec["annual_rate"])
    years = float(spec["years"])
    fv = future_value(pv, rate, years)
    back = present_value(fv, rate, years)
    steps = [
        f"Present amount = {money(pv)}, annual rate = {pct(rate)}, years = {years:g}.",
        "Future value = present × (1 + r)^years.",
        f"Future value = {money(fv)}.",
        f"Discounting that future value back at the same rate returns {money(back)}.",
    ]
    return steps, f"{money(pv)} grows to {money(fv)}.", {"future_value": round(fv, 2)}


def _expectation(spec: dict) -> tuple[list[str], str, dict]:
    outcomes = [(float(p), float(v)) for p, v in spec["outcomes"]]
    ev, sigma = expected_value(outcomes)
    bits = ", ".join(f"{p:.0%} chance of {money(v)}" for p, v in outcomes)
    steps = [
        f"Outcomes: {bits}.",
        "Expected value = sum of probability × value.",
        f"Expected value = {money(ev)}. Standard deviation = {money(sigma)}.",
        "Expected value is the probability-weighted average if the same risk were repeated many times. It is not a guaranteed result.",
    ]
    return steps, f"Expected value {money(ev)}.", {"expected_value": round(ev, 2), "std_dev": round(sigma, 2)}


def _stock(spec: dict) -> tuple[list[str], str, dict]:
    start = float(spec["start"])
    end = float(spec["end"])
    dividend = float(spec.get("dividend", 0))
    simple = simple_return(start, end, dividend)
    log_r = log_return(start, end)
    steps = [
        f"Bought at {money(start)}, price now {money(end)}, dividends received {money(dividend)}.",
        "Simple return = (ending price + dividends − starting price) / starting price.",
        f"Simple return = {simple:.2%}.",
        f"Log price return, ignoring the dividend, is ln(end/start) = {log_r:.2%}. Log returns add across time; simple returns do not.",
    ]
    return steps, f"Simple return {simple:.2%}.", {"simple_return": round(simple, 4)}


def _duration(spec: dict) -> tuple[list[str], str, dict]:
    price = float(spec["price"])
    duration = float(spec["duration"])
    delta = float(spec["yield_change"])
    frac = modified_duration_price_change(duration, delta)
    new_price = price * (1 + frac)
    steps = [
        f"Bond price = {money(price)}, modified duration = {duration:g} years, yield change = {delta:+.2f} percentage points.",
        "Approximate price change ≈ −duration × change in yield.",
        f"Approximate price change = {frac:.2%}, so the price moves to about {money(new_price)}.",
        "This is a straight-line estimate. Large yield moves also need convexity, which this lesson leaves out.",
    ]
    return steps, f"Price moves about {frac:.2%} to {money(new_price)}.", {"new_price": round(new_price, 2)}


def _budget(spec: dict) -> tuple[list[str], str, dict]:
    income = float(spec["income"])
    needs = float(spec["needs"])
    wants = float(spec["wants"])
    savings = float(spec["savings"])
    leftover = income - needs - wants - savings
    steps = [
        f"Monthly take-home pay = {money(income)}.",
        f"Needs {money(needs)}, wants {money(wants)}, savings {money(savings)}.",
        f"Left unassigned = {money(leftover)}.",
        f"Savings rate = {savings / income:.1%} of take-home pay." if income else "Income is zero.",
    ]
    return steps, f"Unassigned cash {money(leftover)}.", {"leftover": round(leftover, 2)}


def _refi(spec: dict) -> tuple[list[str], str, dict]:
    balance = float(spec["balance"])
    old_apr = float(spec["old_apr"])
    new_apr = float(spec["new_apr"])
    months = int(spec["months"])
    old = amortize(balance, old_apr, months)
    new = amortize(balance, new_apr, months)
    saved = old.total_interest - new.total_interest
    steps = [
        f"Balance today = {money(balance)}. Remaining term = {months} months.",
        f"Keeping a {pct(old_apr)} rate means a payment of {money(old.payment)} and interest of {money(old.total_interest)}.",
        f"A new {pct(new_apr)} rate on the same balance and term means a payment of {money(new.payment)} and interest of {money(new.total_interest)}.",
        f"Interest difference over the same term = {money(saved)}. A longer new term can raise total interest even when the payment drops.",
    ]
    return (
        steps,
        f"Same-term refinance changes interest by {money(saved)}.",
        {"old_payment": round(old.payment, 2), "new_payment": round(new.payment, 2), "interest_difference": round(saved, 2)},
    )


RENDERERS = {
    "loan": _loan,
    "apy": _apy,
    "cd": _cd,
    "ira": _ira,
    "utilization": _utilization,
    "depreciation": _depreciation,
    "lease": _lease,
    "tvm": _tvm,
    "expectation": _expectation,
    "stock": _stock,
    "duration": _duration,
    "budget": _budget,
    "refi": _refi,
}


def choice_payment(principal: float, apr: float, months: int) -> float:
    return round(payment(principal, apr, months), 2)
