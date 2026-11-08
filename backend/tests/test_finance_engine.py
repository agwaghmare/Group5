from datetime import date
from decimal import Decimal as D

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.pnc.finance import engine as E
from app.pnc.finance.evidence import ENGINE_VERSION

AS_OF = date(2026, 10, 31)
EVIDENCE_KEYS = {"calculation_id", "as_of_date", "source_type", "inputs", "assumptions", "formula_steps",
                 "intermediate_values", "results", "missing_inputs", "limitations", "engine_version"}


def test_net_worth_and_evidence_schema():
    ev = E.calc_net_worth(AS_OF, [D("1000.50"), D("2000")], [D("500.25")])
    assert ev.results["net_worth"] == "2500.25"
    assert EVIDENCE_KEYS <= set(ev.model_dump())
    assert ev.engine_version == ENGINE_VERSION and ev.formula_steps


def test_calculation_id_is_deterministic():
    a = E.calc_dti(AS_OF, D("1500"), D("5000"))
    b = E.calc_dti(AS_OF, D("1500"), D("5000"))
    c = E.calc_dti(AS_OF, D("1501"), D("5000"))
    assert a.calculation_id == b.calculation_id != c.calculation_id


def test_cash_surplus_and_dti_known_values():
    assert E.calc_cash_surplus(AS_OF, D("5000"), D("3000"), D("800")).results["cash_surplus"] == "1200.00"
    assert E.calc_dti(AS_OF, D("1500"), D("5000")).results["dti"] == "0.3000"


@pytest.mark.parametrize("income", [None, D("0"), D("-5")])
def test_dti_missing_or_invalid_income_reports_missing_not_zero(income):
    ev = E.calc_dti(AS_OF, D("100"), income)
    assert ev.results["dti"] is None and ev.missing_inputs


def test_utilization():
    assert E.calc_utilization(AS_OF, D("2500"), D("10000")).results["utilization"] == "0.2500"
    assert E.calc_utilization(AS_OF, D("2500"), D("0")).results["utilization"] is None


def test_loan_payment_known_value_and_zero_rate():
    # $30,000 at 8% for 60 months -> $608.28 (standard amortisation table value)
    assert E.calc_loan_payment(AS_OF, D("30000"), D("0.08"), 60).results["monthly_payment"] == "608.29"
    zero = E.calc_loan_payment(AS_OF, D("12000"), D("0"), 24)
    assert zero.results["monthly_payment"] == "500.00" and zero.results["total_interest"] == "0.00"


def test_canonical_car_scenario():
    ev = E.calc_purchase_scenario(AS_OF, D("30000"), D("5000"), D("0.08"), 60)
    assert ev.results["financed_amount"] == "25000.00" and ev.results["monthly_payment"] == "506.91"


def test_principal_from_payment_is_inverse_of_payment():
    p = E.principal_from_payment(E.payment(D("18000"), D("0.07"), 48), D("0.07"), 48)
    assert abs(p - D("18000")) < D("0.0001")


def test_amortization_ends_at_zero_and_extra_principal_saves_interest():
    ev = E.calc_amortization(AS_OF, D("10000"), D("0.12"), 36, D("100"))
    sched = ev.results["schedule"]
    assert sched[-1]["balance"] == "0.00"
    assert ev.results["months_saved"] > 0 and D(ev.results["interest_saved"]) > 0
    base = E.calc_amortization(AS_OF, D("10000"), D("0.12"), 36)
    assert base.results["months_saved"] == 0 and len(base.results["schedule"]) == 36


def test_apy_and_savings_growth():
    assert E.calc_apy(AS_OF, D("0.12"), 12).results["apy"] == "0.1268"
    assert E.calc_savings_growth(AS_OF, D("1000"), D("0"), D("0"), 12).results["future_value"] == "1000.00"
    assert E.calc_savings_growth(AS_OF, D("0"), D("100"), D("0"), 12).results["future_value"] == "1200.00"


def test_retirement_real_below_nominal_with_inflation():
    ev = E.calc_retirement_projection(AS_OF, D("10000"), D("500"), D("0.06"), 20, D("0.025"))
    assert D(ev.results["real_balance_today_dollars"]) < D(ev.results["nominal_balance"])


def test_emergency_months():
    assert E.calc_emergency_months(AS_OF, D("9000"), D("3000")).results["months"] == "3.0000"
    assert E.calc_emergency_months(AS_OF, D("9000"), D("0")).missing_inputs


DEBTS = [E.Debt("card", D("3000"), D("0.24"), D("90")), E.Debt("loan", D("8000"), D("0.07"), D("200")),
         E.Debt("small", D("500"), D("0.10"), D("25"))]


def test_avalanche_never_pays_more_interest_than_snowball():
    ev = E.calc_debt_payoff_compare(AS_OF, DEBTS, D("150"))
    assert D(ev.results["avalanche"]["total_interest"]) <= D(ev.results["snowball"]["total_interest"])
    assert ev.results["snowball"]["converged"] and ev.results["avalanche"]["converged"]
    assert ev.results["snowball"]["payoff_order"][0]["debt"] == "small"          # smallest balance first


def test_stress_test_runway_and_self_funding():
    ev = E.calc_stress_test(AS_OF, D("6000"), D("4000"), D("2500"), D("500"), D("0.5"), D("0.1"))
    assert ev.results["status"] == "drawdown" and ev.results["monthly_burn"] == "1250.00"
    assert ev.results["runway_months"] == "4.8000"
    ok = E.calc_stress_test(AS_OF, D("100"), D("4000"), D("1000"), D("0"), D("0"), D("0"))
    assert ok.results["status"] == "self_funding" and ok.results["runway_months"] is None


def test_npv_and_goal_contribution():
    assert E.calc_npv(AS_OF, D("0"), [D("-100"), D("50"), D("60")]).results["npv"] == "10.00"
    g = E.calc_goal_contribution(AS_OF, D("12000"), D("0"), 12)
    assert g.results["required_monthly"] == "1000.00"
    done = E.calc_goal_contribution(AS_OF, D("1000"), D("2000"), 12)
    assert done.results["required_monthly"] == "0.00" and done.results["already_funded"] is True
    assert E.calc_goal_contribution(AS_OF, D("1000"), D("0"), 0).missing_inputs


@settings(max_examples=60, deadline=None)
@given(p=st.decimals(min_value=500, max_value=500000, places=2), r=st.decimals(min_value=0, max_value="0.35", places=4),
       n=st.integers(min_value=6, max_value=360))
def test_property_amortization_conserves_principal(p, r, n):
    rows = E.amortize(p, r, n)
    assert abs(sum(x.principal for x in rows) - p) < D("0.01")
    assert rows[-1].balance == 0
    assert all(x.balance >= 0 for x in rows)


@settings(max_examples=60, deadline=None)
@given(p=st.decimals(min_value=500, max_value=500000, places=2), r=st.decimals(min_value=0, max_value="0.35", places=4),
       n=st.integers(min_value=6, max_value=360), extra=st.decimals(min_value=0, max_value=2000, places=2))
def test_property_extra_payment_never_costs_more(p, r, n, extra):
    base, ext = E.amortize(p, r, n), E.amortize(p, r, n, extra)
    assert len(ext) <= len(base)
    assert sum(x.interest for x in ext) <= sum(x.interest for x in base) + D("0.0001")


@settings(max_examples=60, deadline=None)
@given(t=st.decimals(min_value=100, max_value=200000, places=2), months=st.integers(min_value=1, max_value=240),
       r=st.decimals(min_value=0, max_value="0.2", places=4))
def test_property_goal_contribution_reaches_target(t, months, r):
    need = E.calc_goal_contribution(AS_OF, t, D(0), months, r).results["required_monthly"]
    reached = E.future_value(D(0), D(need), r, months)
    assert abs(reached - t) < D("0.05") * months   # cent rounding of the contribution, bounded
