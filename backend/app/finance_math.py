"""Closed-form money math used by lessons and the decision explainer.

Formulas
--------
Monthly loan payment (ordinary annuity):
    r = APR / 12
    M = P * r * (1 + r)^n / ((1 + r)^n - 1)

APY from a nominal rate compounded n times a year:
    APY = (1 + nominal / n)^n - 1
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def money(amount: float) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def pct(rate: float, digits: int = 2) -> str:
    return f"{rate:.{digits}f}%"


def monthly_rate(apr_percent: float) -> float:
    return apr_percent / 100.0 / 12.0


def payment(principal: float, apr_percent: float, months: int) -> float:
    """Fixed monthly payment that amortizes `principal` over `months`."""
    if months <= 0 or principal <= 0:
        return 0.0
    r = monthly_rate(apr_percent)
    if r <= 0:
        return principal / months
    growth = (1.0 + r) ** months
    return principal * r * growth / (growth - 1.0)


@dataclass(frozen=True)
class Amortization:
    payment: float
    months: int
    total_paid: float
    total_interest: float
    first_interest: float
    first_principal: float
    balance_after_first: float


def simulate(
    balance: float,
    apr_percent: float,
    contractual_payment: float,
    extra: float = 0.0,
    max_months: int = 1200,
) -> Amortization:
    """Apply a fixed payment (plus optional extra principal) until the balance is gone."""
    r = monthly_rate(apr_percent)
    bal = max(0.0, balance)
    if bal == 0 or contractual_payment <= 0:
        return Amortization(contractual_payment, 0, 0.0, 0.0, 0.0, 0.0, bal)

    total_paid = 0.0
    total_interest = 0.0
    first_interest = 0.0
    first_principal = 0.0
    months = 0
    while bal > 0.005 and months < max_months:
        interest = bal * r
        due = contractual_payment + extra
        # Last payment is smaller and never includes extra beyond the balance.
        pay = min(due, bal + interest)
        principal_paid = pay - interest
        if principal_paid <= 0 and bal > 0.005:
            break
        bal = max(0.0, bal - principal_paid)
        total_paid += pay
        total_interest += interest
        if months == 0:
            first_interest = interest
            first_principal = principal_paid
        months += 1
    return Amortization(
        payment=contractual_payment,
        months=months,
        total_paid=total_paid,
        total_interest=total_interest,
        first_interest=first_interest,
        first_principal=first_principal,
        balance_after_first=max(0.0, balance - first_principal) if months else balance,
    )


def amortize(principal: float, apr_percent: float, months: int, extra: float = 0.0) -> Amortization:
    pmt = payment(principal, apr_percent, months)
    return simulate(principal, apr_percent, pmt, extra=extra)


def apy_from_nominal(nominal_percent: float, compounds_per_year: int) -> float:
    if compounds_per_year <= 0:
        return nominal_percent / 100.0
    r = nominal_percent / 100.0
    return (1.0 + r / compounds_per_year) ** compounds_per_year - 1.0


def future_value(present: float, annual_yield: float, years: float) -> float:
    """`annual_yield` is an effective annual rate as a percent (an APY)."""
    return present * (1.0 + annual_yield / 100.0) ** years


def present_value(future: float, annual_yield: float, years: float) -> float:
    return future / (1.0 + annual_yield / 100.0) ** years


def annuity_future_value(annual_contribution: float, annual_yield: float, years: int) -> float:
    """Future value of a contribution made at the end of each year."""
    r = annual_yield / 100.0
    if years <= 0:
        return 0.0
    if abs(r) < 1e-12:
        return annual_contribution * years
    return annual_contribution * ((1.0 + r) ** years - 1.0) / r


def simple_return(start_price: float, end_price: float, dividend: float = 0.0) -> float:
    return (end_price + dividend - start_price) / start_price


def log_return(start_price: float, end_price: float) -> float:
    return math.log(end_price / start_price)


def expected_value(outcomes: list[tuple[float, float]]) -> tuple[float, float]:
    """Return (mean, standard deviation) for (probability, value) pairs."""
    total_p = sum(p for p, _ in outcomes)
    if total_p <= 0:
        return 0.0, 0.0
    ev = sum(p * v for p, v in outcomes) / total_p
    var = sum(p * (v - ev) ** 2 for p, v in outcomes) / total_p
    return ev, math.sqrt(var)


def modified_duration_price_change(duration_years: float, yield_change_percent_points: float) -> float:
    """Approximate fractional price change: -duration × Δyield."""
    return -duration_years * (yield_change_percent_points / 100.0)


def money_factor_to_apr(factor: float) -> float:
    """Industry approximation: APR ≈ money_factor × 2400."""
    return factor * 2400.0


def lease_parts(
    cap_cost: float, residual: float, term_months: int, money_factor: float
) -> tuple[float, float, float]:
    """Return (depreciation, rent_charge, base_payment) for a lease."""
    dep = (cap_cost - residual) / term_months if term_months else 0.0
    rent = (cap_cost + residual) * money_factor
    return dep, rent, dep + rent
