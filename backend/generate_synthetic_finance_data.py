"""Generate realistic synthetic personal finance tracker data."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

np.random.seed(42)

N_USERS = 500
N_MONTHS = 6  # 3000 rows
START = datetime(2024, 1, 1)

PAY_FREQS = np.array(["weekly", "biweekly", "semimonthly", "monthly"])
LIFE_EVENTS = np.array(
    [
        "none",
        "new_job",
        "job_loss",
        "move",
        "marriage",
        "divorce",
        "new_child",
        "retirement",
        "remote_work",
        "college",
    ]
)


def month_add(dt: datetime, months: int) -> datetime:
    year = dt.year + (dt.month - 1 + months) // 12
    month = (dt.month - 1 + months) % 12 + 1
    return datetime(year, month, 1)


def build_personas(n_users: int) -> list[dict]:
    personas: list[dict] = []
    for uid in range(1000, 1000 + n_users):
        base_income = float(np.clip(np.random.lognormal(mean=8.2, sigma=0.45), 1800, 18000))
        income_type_w = np.random.choice(["stable", "variable", "gig"], p=[0.62, 0.25, 0.13])
        credit_score = int(np.clip(np.random.normal(700, 55), 520, 850))
        has_mortgage = np.random.rand() < (0.25 + 0.45 * min(1.0, (base_income - 2500) / 8000))
        owns_investments = np.random.rand() < (0.35 + 0.5 * min(1.0, (base_income - 2000) / 9000))
        pay_frequency = np.random.choice(PAY_FREQS, p=[0.12, 0.48, 0.18, 0.22])
        months_employed_base = int(np.clip(np.random.exponential(36) + 1, 1, 240))
        discipline = float(np.clip(np.random.beta(2.2, 2.0), 0.05, 0.98))
        risk_tol = float(np.clip(np.random.beta(2.0, 2.2), 0.05, 0.98))
        col_index = float(np.clip(np.random.normal(1.0, 0.18), 0.7, 1.55))
        personas.append(
            dict(
                user_id=uid,
                base_income=base_income,
                income_type_w=income_type_w,
                credit_score=credit_score,
                has_mortgage=has_mortgage,
                owns_investments=owns_investments,
                pay_frequency=pay_frequency,
                months_employed_base=months_employed_base,
                discipline=discipline,
                risk_tol=risk_tol,
                col_index=col_index,
                savings0=max(0.0, np.random.lognormal(8.0 + discipline, 1.1) * (0.4 + 0.8 * discipline)),
                checking0=max(50.0, np.random.lognormal(7.2, 0.7)),
                debt0=max(
                    0.0,
                    np.random.lognormal(8.5, 1.0)
                    * (1.3 - 0.7 * discipline)
                    * (1.1 - (credit_score - 520) / 500),
                ),
                portfolio0=(
                    max(0.0, np.random.lognormal(9.5, 1.2))
                    if owns_investments
                    else max(0.0, np.random.lognormal(6.5, 1.0) * 0.3)
                ),
                home_value0=(
                    float(np.clip(np.random.lognormal(12.6, 0.35) * col_index, 120000, 1400000))
                    if has_mortgage
                    else 0.0
                ),
                mortgage_ltv0=(
                    float(np.clip(np.random.normal(0.72, 0.12), 0.35, 0.95)) if has_mortgage else 0.0
                ),
                mortgage_rate0=(
                    float(np.clip(np.random.normal(5.8, 1.1), 2.75, 8.5)) if has_mortgage else 0.0
                ),
                cc_limit0=float(
                    np.clip(
                        np.random.lognormal(8.6 + (credit_score - 650) / 180, 0.55),
                        500,
                        75000,
                    )
                ),
                life_event_bias=np.random.choice(
                    LIFE_EVENTS,
                    p=[0.55, 0.08, 0.04, 0.07, 0.05, 0.03, 0.06, 0.03, 0.05, 0.04],
                ),
            )
        )
    return personas


def generate(n_users: int = N_USERS, n_months: int = N_MONTHS) -> pd.DataFrame:
    personas = build_personas(n_users)
    rows: list[dict] = []

    for p in personas:
        income = p["base_income"]
        savings = p["savings0"]
        checking = p["checking0"]
        debt = p["debt0"]
        portfolio = p["portfolio0"]
        home_value = p["home_value0"]
        mortgage_bal = home_value * p["mortgage_ltv0"] if p["has_mortgage"] else 0.0
        mortgage_rate = p["mortgage_rate0"]
        cc_limit = p["cc_limit0"]
        util = float(np.clip(np.random.beta(2.0, 3.5) * (1.15 - p["discipline"] * 0.5), 0.01, 0.98))
        months_emp = p["months_employed_base"]
        savings_streak = int(np.clip(np.random.poisson(p["discipline"] * 8), 0, 36))
        late_pays = int(
            np.clip(
                np.random.poisson((1 - p["discipline"]) * 1.8 + (1 if p["credit_score"] < 620 else 0)),
                0,
                8,
            )
        )
        overdrafts = 0
        income_hist: list[float] = []
        spend_hist: list[float] = []

        for m in range(n_months):
            date = month_add(START, m)

            if m == 0:
                life_event = "none" if np.random.rand() < 0.7 else p["life_event_bias"]
            else:
                life_event = np.random.choice(
                    LIFE_EVENTS,
                    p=[0.82, 0.03, 0.02, 0.03, 0.02, 0.01, 0.02, 0.01, 0.02, 0.02],
                )
                if life_event == p["life_event_bias"] and np.random.rand() < 0.25:
                    life_event = p["life_event_bias"]

            vol_base = {"stable": 0.04, "variable": 0.14, "gig": 0.28}[p["income_type_w"]]
            shock = np.random.normal(0, vol_base)
            if life_event == "job_loss":
                shock -= 0.55
            elif life_event == "new_job":
                shock += 0.12
            elif life_event == "retirement":
                shock -= 0.35
            income = float(np.clip(income * (1 + shock), 800, 25000))
            income_hist.append(income)

            if len(income_hist) >= 2:
                income_volatility_3m = float(
                    np.std(income_hist[-3:]) / max(np.mean(income_hist[-3:]), 1.0)
                )
                growth = (income_hist[-1] / income_hist[0]) - 1.0
                months_span = max(1, len(income_hist) - 1)
                income_growth_6m = float(growth * (6 / months_span))
            else:
                income_volatility_3m = float(abs(shock))
                income_growth_6m = float(np.random.normal(0.02, 0.04))

            if life_event == "job_loss":
                months_emp = max(0, int(np.random.randint(0, 3)))
            elif life_event == "new_job":
                months_emp = int(np.random.randint(1, 4))
            else:
                months_emp += 1

            housing_rent = (
                0.0
                if p["has_mortgage"]
                else float(
                    np.clip(
                        income * np.random.uniform(0.22, 0.38) * p["col_index"] / 1.1,
                        500,
                        4500,
                    )
                )
            )
            mortgage_payment = 0.0
            if p["has_mortgage"] and mortgage_bal > 0:
                r = mortgage_rate / 100 / 12
                if r > 0:
                    mortgage_payment = float(
                        np.clip(
                            mortgage_bal * (r * (1 + r) ** 240) / ((1 + r) ** 240 - 1),
                            600,
                            6500,
                        )
                    )
                else:
                    mortgage_payment = float(np.clip(mortgage_bal / 240, 600, 6500))

            weighted_avg_apr = float(
                np.clip(np.random.normal(9.5 - (p["credit_score"] - 650) * 0.02, 3.2), 3.5, 28)
            )
            min_debt_payment = float(
                max(0.0, debt * np.random.uniform(0.015, 0.035) + (25 if debt > 0 else 0))
            )
            remaining_loan_term = int(np.clip(np.random.normal(42, 18), 0, 84)) if debt > 100 else 0

            subscription_cost = float(
                np.clip(
                    np.random.gamma(3.5, 18) * (0.7 + 0.6 * (1 - p["discipline"])),
                    0,
                    450,
                )
            )
            recurring_bills = float(
                housing_rent
                + mortgage_payment
                + subscription_cost
                + min_debt_payment
                + np.random.uniform(120, 420)
            )

            essential = float(recurring_bills + np.random.uniform(200, 900))
            discretionary = float(
                np.clip(
                    income * np.random.uniform(0.08, 0.28) * (1.2 - p["discipline"]),
                    50,
                    income * 0.55,
                )
            )
            monthly_spend = essential + discretionary
            spend_hist.append(monthly_spend)
            if len(spend_hist) >= 2:
                spending_volatility_3m = float(
                    np.std(spend_hist[-3:]) / max(np.mean(spend_hist[-3:]), 1.0)
                )
            else:
                spending_volatility_3m = float(np.random.uniform(0.05, 0.25))

            budget_target = income * (0.55 + 0.25 * p["discipline"])
            budget_variance_pct = float(
                np.clip((monthly_spend - budget_target) / max(budget_target, 1) * 100, -60, 80)
            )

            net = income - monthly_spend
            monthly_savings_contribution = float(
                max(0.0, net * (0.15 + 0.55 * p["discipline"]) + np.random.normal(0, 40))
            )
            if net < 0:
                monthly_savings_contribution = float(max(0.0, monthly_savings_contribution * 0.2))
                checking += net
                if checking < 0:
                    overdrafts = min(12, overdrafts + (1 if np.random.rand() < 0.7 else 0))
                    transfer = min(savings * 0.25, abs(checking) + np.random.uniform(50, 300))
                    savings = max(0.0, savings - transfer)
                    checking += transfer + np.random.uniform(0, 150)
            else:
                checking += net - monthly_savings_contribution
                savings += monthly_savings_contribution
                if monthly_savings_contribution > 50:
                    savings_streak += 1
                else:
                    savings_streak = 0

            checking = float(np.clip(checking + np.random.normal(0, 40), -200, 85000))
            savings = float(np.clip(savings + np.random.normal(0, 30), 0, 350000))
            pending = float(np.clip(np.random.gamma(2.0, 35), 0, max(0.0, checking * 0.35)))
            available_balance = float(max(-250.0, checking - pending))
            overdraft_count_90d = int(
                np.clip(overdrafts if m < 3 else max(0, overdrafts - np.random.randint(0, 2)), 0, 12)
            )

            savings_apy = float(np.clip(np.random.normal(4.2, 0.55), 0.01, 5.5))
            emergency_fund_months = float(np.clip(savings / max(essential, 1.0), 0, 36))

            debt = float(
                max(
                    0.0,
                    debt * (1 + weighted_avg_apr / 100 / 12)
                    - min_debt_payment
                    + np.random.uniform(-80, 220) * (1 - p["discipline"]),
                )
            )
            if life_event in ("divorce", "job_loss", "new_child"):
                debt += np.random.uniform(500, 4500) * (0.5 + np.random.rand())

            util = float(
                np.clip(
                    util
                    + np.random.normal(0, 0.04)
                    + (0.08 if net < 0 else -0.02 * p["discipline"]),
                    0.0,
                    1.0,
                )
            )
            credit_limit_total = float(np.clip(cc_limit * (1 + np.random.normal(0, 0.01)), 300, 100000))
            if p["credit_score"] > 720 and np.random.rand() < 0.08:
                credit_limit_total *= 1.05
                cc_limit = credit_limit_total
            credit_card_apr = float(
                np.clip(np.random.normal(22.5 - (p["credit_score"] - 650) * 0.03, 3.5), 12.0, 29.99)
            )
            if util > 0.7 and np.random.rand() < 0.15:
                late_pays = min(12, late_pays + 1)
            elif util < 0.3 and late_pays > 0 and np.random.rand() < 0.2:
                late_pays = max(0, late_pays - 1)
            late_payments_12m = int(np.clip(late_pays, 0, 12))

            if p["has_mortgage"]:
                home_value = float(np.clip(home_value * (1 + np.random.normal(0.002, 0.008)), 80000, 1600000))
                principal_pay = mortgage_payment * np.random.uniform(0.25, 0.45) if mortgage_payment else 0.0
                mortgage_bal = float(max(0.0, mortgage_bal - principal_pay + np.random.normal(0, 20)))
                home_equity = float(max(0.0, home_value - mortgage_bal))
                mortgage_interest_rate = float(np.clip(mortgage_rate + np.random.normal(0, 0.02), 2.5, 9.0))
            else:
                home_value = 0.0
                mortgage_bal = 0.0
                home_equity = 0.0
                mortgage_interest_rate = 0.0

            market = np.random.normal(0.006, 0.035)
            equity_allocation_pct = float(np.clip(40 + p["risk_tol"] * 50 + np.random.normal(0, 4), 5, 95))
            investment_volatility = float(
                np.clip(
                    0.08 + equity_allocation_pct / 100 * 0.18 + abs(np.random.normal(0, 0.02)),
                    0.05,
                    0.45,
                )
            )
            retirement_contribution = float(max(0.0, income * np.random.uniform(0.03, 0.12) * p["discipline"]))
            if p["owns_investments"] or retirement_contribution > 50:
                portfolio = float(
                    max(0.0, portfolio * (1 + market * (equity_allocation_pct / 100)) + retirement_contribution)
                )
            else:
                portfolio = float(
                    max(0.0, portfolio * (1 + market * 0.3) + retirement_contribution * 0.5)
                )

            txn_velocity = int(
                np.clip(
                    np.random.poisson(4 + (3 if life_event != "none" else 0) + discretionary / 200),
                    0,
                    40,
                )
            )
            zscore = float(np.random.normal(0, 1))
            unusual = 0
            merch_change = 0
            if np.random.rand() < 0.025:
                unusual = 1
                merch_change = 1 if np.random.rand() < 0.8 else 0
                zscore = float(np.clip(np.random.normal(3.2, 0.8), 1.8, 7))
                txn_velocity = int(np.clip(txn_velocity + np.random.randint(5, 18), 0, 50))
            elif np.random.rand() < 0.06:
                merch_change = 1
                zscore = float(np.random.normal(1.2, 0.6))

            monthly_obligations = recurring_bills + (
                credit_limit_total * util * credit_card_apr / 100 / 12
            )
            liquidity_runway_months = float(
                np.clip((checking + savings) / max(monthly_obligations, 1.0), 0, 48)
            )
            projected_balance_30d = float(checking + income - monthly_spend)
            debt_service = (
                mortgage_payment
                + min_debt_payment
                + (credit_limit_total * util * 0.02)
            )
            debt_service_coverage = float(np.clip(income / max(debt_service, 1.0), 0, 20))
            bill_payment_delay_count = int(
                np.clip(
                    np.random.poisson(
                        max(
                            0.0,
                            (1.2 - p["discipline"]) * 1.5
                            + (0.8 if liquidity_runway_months < 1 else 0)
                            + late_payments_12m * 0.15,
                        )
                    ),
                    0,
                    10,
                )
            )

            rows.append(
                dict(
                    date=date.strftime("%Y-%m-%d"),
                    user_id=p["user_id"],
                    monthly_income=round(income, 2),
                    income_volatility_3m=round(income_volatility_3m, 4),
                    income_growth_6m=round(income_growth_6m, 4),
                    pay_frequency=p["pay_frequency"],
                    months_employed=int(months_emp),
                    checking_balance=round(checking, 2),
                    available_balance=round(available_balance, 2),
                    overdraft_count_90d=int(overdraft_count_90d),
                    recurring_bill_total=round(recurring_bills, 2),
                    savings_balance=round(savings, 2),
                    savings_apy=round(savings_apy, 2),
                    emergency_fund_months=round(emergency_fund_months, 2),
                    monthly_savings_contribution=round(monthly_savings_contribution, 2),
                    total_debt_balance=round(debt, 2),
                    weighted_avg_apr=round(weighted_avg_apr, 2),
                    minimum_debt_payment=round(min_debt_payment, 2),
                    remaining_loan_term_months=int(remaining_loan_term),
                    credit_limit_total=round(credit_limit_total, 2),
                    credit_utilization=round(util, 4),
                    credit_card_apr=round(credit_card_apr, 2),
                    late_payments_12m=int(late_payments_12m),
                    home_value=round(home_value, 2),
                    mortgage_balance=round(mortgage_bal, 2),
                    mortgage_interest_rate=round(mortgage_interest_rate, 3),
                    home_equity=round(home_equity if p["has_mortgage"] else 0.0, 2),
                    portfolio_value=round(portfolio, 2),
                    equity_allocation_pct=round(equity_allocation_pct, 2),
                    retirement_contribution=round(retirement_contribution, 2),
                    investment_volatility=round(investment_volatility, 4),
                    subscription_cost_monthly=round(subscription_cost, 2),
                    spending_volatility_3m=round(spending_volatility_3m, 4),
                    budget_variance_pct=round(budget_variance_pct, 2),
                    savings_streak_months=int(np.clip(savings_streak, 0, 60)),
                    unusual_merchant_flag=int(unusual),
                    transaction_amount_zscore=round(zscore, 3),
                    transaction_velocity_24h=int(txn_velocity),
                    merchant_category_change=int(merch_change),
                    liquidity_runway_months=round(liquidity_runway_months, 2),
                    projected_balance_30d=round(projected_balance_30d, 2),
                    debt_service_coverage=round(debt_service_coverage, 3),
                    bill_payment_delay_count=int(bill_payment_delay_count),
                    life_event_type=life_event,
                )
            )

    return pd.DataFrame(rows)


def validate(df: pd.DataFrame) -> None:
    assert len(df) == N_USERS * N_MONTHS
    assert (df["available_balance"] <= df["checking_balance"] + 1e-6).mean() > 0.98
    mortgage = df[df["home_value"] > 0]
    assert ((mortgage["home_equity"] - (mortgage["home_value"] - mortgage["mortgage_balance"])).abs() < 1.0).all()
    assert df["credit_utilization"].between(0, 1.0001).all()
    assert df["unusual_merchant_flag"].isin([0, 1]).all()
    assert set(df["pay_frequency"]).issubset(set(PAY_FREQS))
    assert set(df["life_event_type"]).issubset(set(LIFE_EVENTS))


if __name__ == "__main__":
    # Vehicle / TFS fields live in data/vehicles.csv + the Toyota next-move pack — not here.
    out = r"c:\Group5\data\personal_finance_tracker_dataset.csv"
    df = generate()
    validate(df)
    df.to_csv(out, index=False)
    print(f"wrote {out}")
    print(f"shape={df.shape}")
    print("columns=", list(df.columns))
    print(df.describe().T[["mean", "min", "max"]].to_string())
    print("\npay_frequency:\n", df["pay_frequency"].value_counts().to_string())
    print("\nlife_event_type:\n", df["life_event_type"].value_counts().to_string())
    print("fraud_rate=", round(df["unusual_merchant_flag"].mean(), 4))
    print("mortgage_share=", round((df["home_value"] > 0).mean(), 4))
    print("\nsample:\n", df.head(2).to_string())
