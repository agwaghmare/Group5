"""
Load Group5 datasets into Tiger Cloud (TimescaleDB).

Schemas:
  toyota   - Smartest Next Move pack (normalized tables + profile view)
  finance  - personal finance tracker monthly snapshots (hypertable)
  meta     - dataset catalog / provenance

Sources under data/:
  CSVs are loaded. customer_profiles.json and toyota_next_move_data_pack.xlsx
  are the same Toyota pack (denormalized / workbook) and are registered in
  meta.dataset_catalog but not duplicated as tables.
"""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SERVICE_ID = "ernvuaxenn"


def tiger_uri() -> str:
    result = subprocess.run(
        ["tiger", "db", "uri", SERVICE_ID, "--with-password"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"tiger db uri failed: {result.stderr or result.stdout}")
    uri = (result.stdout or "").strip().splitlines()[-1].strip()
    if not uri.startswith("postgresql://"):
        raise RuntimeError(f"unexpected connection URI: {uri[:40]}...")
    return uri


def yn_to_bool(series: pd.Series) -> pd.Series:
    return series.map({"Y": True, "N": False, "y": True, "n": False})


DDL = """
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE SCHEMA IF NOT EXISTS toyota;
CREATE SCHEMA IF NOT EXISTS finance;
CREATE SCHEMA IF NOT EXISTS meta;

DROP VIEW IF EXISTS toyota.customer_profiles CASCADE;
DROP TABLE IF EXISTS toyota.option_scenarios CASCADE;
DROP TABLE IF EXISTS toyota.golden_answers CASCADE;
DROP TABLE IF EXISTS toyota.situations CASCADE;
DROP TABLE IF EXISTS toyota.accounts CASCADE;
DROP TABLE IF EXISTS toyota.vehicles CASCADE;
DROP TABLE IF EXISTS toyota.customers CASCADE;
DROP TABLE IF EXISTS toyota.offers_catalog CASCADE;
DROP TABLE IF EXISTS toyota.rate_sheet CASCADE;
DROP TABLE IF EXISTS toyota.value_drivers CASCADE;
DROP TABLE IF EXISTS finance.monthly_snapshots CASCADE;
DROP TABLE IF EXISTS meta.dataset_catalog CASCADE;

CREATE TABLE meta.dataset_catalog (
    dataset_key       TEXT PRIMARY KEY,
    schema_name       TEXT NOT NULL,
    table_name        TEXT,
    source_file       TEXT NOT NULL,
    description       TEXT NOT NULL,
    loaded_as_table   BOOLEAN NOT NULL DEFAULT TRUE,
    notes             TEXT
);

CREATE TABLE toyota.customers (
    customer_id                 TEXT PRIMARY KEY,
    payday_day                  SMALLINT NOT NULL,
    first_name                  TEXT NOT NULL,
    age                         SMALLINT NOT NULL,
    city                        TEXT NOT NULL,
    state                       CHAR(2) NOT NULL,
    occupation                  TEXT NOT NULL,
    annual_income               NUMERIC(12, 2) NOT NULL,
    credit_tier_at_origination  CHAR(1) NOT NULL,
    credit_tier_now             CHAR(1) NOT NULL,
    other_monthly_debt          NUMERIC(12, 2) NOT NULL,
    tenure_months_with_tfs      INTEGER NOT NULL,
    autopay                     BOOLEAN NOT NULL,
    digital_engagement          TEXT NOT NULL,
    preferred_channel           TEXT NOT NULL,
    marketing_consent           BOOLEAN NOT NULL,
    vulnerable_flag             BOOLEAN NOT NULL,
    payment_to_income_pct       NUMERIC(6, 2) NOT NULL,
    debt_to_income_pct          NUMERIC(6, 2) NOT NULL,
    financial_stress_score      SMALLINT NOT NULL CHECK (financial_stress_score BETWEEN 0 AND 100)
);

CREATE TABLE toyota.vehicles (
    vehicle_id              TEXT PRIMARY KEY,
    customer_id             TEXT NOT NULL REFERENCES toyota.customers (customer_id),
    model_year              SMALLINT NOT NULL,
    model                   TEXT NOT NULL,
    trim                    TEXT NOT NULL,
    condition_at_purchase   TEXT NOT NULL,
    purchase_price_or_msrp  NUMERIC(12, 2) NOT NULL,
    odometer_now            INTEGER NOT NULL,
    annual_miles_est        INTEGER NOT NULL,
    est_market_value_now    NUMERIC(12, 2) NOT NULL,
    toyota_care_ends        DATE,
    basic_warranty_ends     DATE,
    last_service_date       DATE,
    next_service_due        DATE,
    open_recall             BOOLEAN NOT NULL
);

CREATE UNIQUE INDEX vehicles_one_per_customer ON toyota.vehicles (customer_id);

CREATE TABLE toyota.accounts (
    account_id              TEXT PRIMARY KEY,
    customer_id             TEXT NOT NULL REFERENCES toyota.customers (customer_id),
    vehicle_id              TEXT NOT NULL REFERENCES toyota.vehicles (vehicle_id),
    contract_type           TEXT NOT NULL CHECK (contract_type IN ('loan', 'lease')),
    contract_start          DATE NOT NULL,
    term_months             INTEGER NOT NULL,
    months_elapsed          INTEGER NOT NULL,
    months_remaining        INTEGER NOT NULL,
    contract_end            DATE NOT NULL,
    missed_payments_12m     SMALLINT NOT NULL,
    autopay                 BOOLEAN NOT NULL,
    amount_financed         NUMERIC(12, 2) NOT NULL,
    apr                     NUMERIC(6, 3),
    money_factor            NUMERIC(10, 6),
    monthly_payment         NUMERIC(12, 2) NOT NULL,
    current_balance         NUMERIC(12, 2),
    payoff_quote            NUMERIC(12, 2),
    residual_value          NUMERIC(12, 2),
    mileage_allowance_total INTEGER,
    est_equity              NUMERIC(12, 2),
    payment_due_day         SMALLINT NOT NULL
);

CREATE UNIQUE INDEX accounts_one_per_customer ON toyota.accounts (customer_id);

CREATE TABLE toyota.situations (
    situation_id     TEXT PRIMARY KEY,
    customer_id      TEXT NOT NULL UNIQUE REFERENCES toyota.customers (customer_id),
    customer_says    TEXT NOT NULL,
    context_summary  TEXT NOT NULL
);

CREATE TABLE toyota.offers_catalog (
    offer_id                 TEXT PRIMARY KEY,
    offer_name               TEXT NOT NULL,
    next_step_type           TEXT NOT NULL,
    eligibility_rule_summary TEXT NOT NULL,
    business_value           TEXT NOT NULL,
    service_effort           TEXT NOT NULL
);

CREATE TABLE toyota.rate_sheet (
    credit_tier      CHAR(1) NOT NULL,
    tier_label       TEXT NOT NULL,
    term_months      INTEGER NOT NULL,
    new_purchase_apr NUMERIC(6, 3) NOT NULL,
    refinance_apr    NUMERIC(6, 3) NOT NULL,
    PRIMARY KEY (credit_tier, term_months)
);

CREATE TABLE toyota.value_drivers (
    driver_id        TEXT PRIMARY KEY,
    description      TEXT NOT NULL,
    assumption_text  TEXT NOT NULL,
    value_usd        NUMERIC(12, 2) NOT NULL,
    value_type       TEXT NOT NULL
);

CREATE TABLE toyota.option_scenarios (
    customer_id              TEXT NOT NULL REFERENCES toyota.customers (customer_id),
    option_id                TEXT NOT NULL,
    option_name              TEXT NOT NULL,
    new_monthly_payment      NUMERIC(12, 2),
    monthly_payment_change   NUMERIC(12, 2),
    upfront_cost             NUMERIC(12, 2),
    total_cost_vs_keep_as_is NUMERIC(12, 2),
    eligibility              TEXT NOT NULL,
    plain_language_summary   TEXT NOT NULL,
    key_assumption           TEXT NOT NULL,
    tradeoff                 TEXT NOT NULL,
    PRIMARY KEY (customer_id, option_id)
);

CREATE TABLE toyota.golden_answers (
    customer_id              TEXT PRIMARY KEY REFERENCES toyota.customers (customer_id),
    best_next_move           TEXT NOT NULL,
    next_step_type           TEXT NOT NULL CHECK (next_step_type IN ('Self-service', 'Follow-up', 'Offer')),
    offer_id                 TEXT REFERENCES toyota.offers_catalog (offer_id),
    plain_language_message   TEXT NOT NULL,
    why_not_the_others       TEXT NOT NULL,
    guardrail_notes          TEXT NOT NULL,
    value_driver_ids         TEXT NOT NULL,
    value_if_completed_usd   NUMERIC(12, 2) NOT NULL,
    assumed_take_rate        NUMERIC(5, 4) NOT NULL,
    expected_value_usd       NUMERIC(12, 2) NOT NULL
);

CREATE TABLE finance.monthly_snapshots (
    snapshot_date                TIMESTAMPTZ NOT NULL,
    user_id                      BIGINT NOT NULL,
    monthly_income               DOUBLE PRECISION,
    income_volatility_3m         DOUBLE PRECISION,
    income_growth_6m             DOUBLE PRECISION,
    pay_frequency                TEXT,
    months_employed              INTEGER,
    checking_balance             DOUBLE PRECISION,
    available_balance            DOUBLE PRECISION,
    overdraft_count_90d          INTEGER,
    recurring_bill_total         DOUBLE PRECISION,
    savings_balance              DOUBLE PRECISION,
    savings_apy                  DOUBLE PRECISION,
    emergency_fund_months        DOUBLE PRECISION,
    monthly_savings_contribution DOUBLE PRECISION,
    total_debt_balance           DOUBLE PRECISION,
    weighted_avg_apr             DOUBLE PRECISION,
    minimum_debt_payment         DOUBLE PRECISION,
    remaining_loan_term_months   INTEGER,
    credit_limit_total           DOUBLE PRECISION,
    credit_utilization           DOUBLE PRECISION,
    credit_card_apr              DOUBLE PRECISION,
    late_payments_12m            INTEGER,
    home_value                   DOUBLE PRECISION,
    mortgage_balance             DOUBLE PRECISION,
    mortgage_interest_rate       DOUBLE PRECISION,
    home_equity                  DOUBLE PRECISION,
    portfolio_value              DOUBLE PRECISION,
    equity_allocation_pct        DOUBLE PRECISION,
    retirement_contribution      DOUBLE PRECISION,
    investment_volatility        DOUBLE PRECISION,
    subscription_cost_monthly    DOUBLE PRECISION,
    spending_volatility_3m       DOUBLE PRECISION,
    budget_variance_pct          DOUBLE PRECISION,
    savings_streak_months        INTEGER,
    unusual_merchant_flag        SMALLINT,
    transaction_amount_zscore    DOUBLE PRECISION,
    transaction_velocity_24h     INTEGER,
    merchant_category_change     SMALLINT,
    liquidity_runway_months      DOUBLE PRECISION,
    projected_balance_30d        DOUBLE PRECISION,
    debt_service_coverage        DOUBLE PRECISION,
    bill_payment_delay_count     INTEGER,
    life_event_type              TEXT,
    PRIMARY KEY (user_id, snapshot_date)
) WITH (
    tsdb.hypertable,
    tsdb.partition_column = 'snapshot_date',
    tsdb.segmentby = 'user_id',
    tsdb.orderby = 'snapshot_date DESC',
    tsdb.chunk_interval = '1 month'
);

CREATE INDEX monthly_snapshots_date_idx
    ON finance.monthly_snapshots (snapshot_date DESC);

CREATE OR REPLACE VIEW toyota.customer_profiles AS
SELECT
    c.customer_id,
    jsonb_build_object(
        'customer_id', c.customer_id,
        'payday_day', c.payday_day,
        'first_name', c.first_name,
        'age', c.age,
        'city', c.city,
        'state', c.state,
        'occupation', c.occupation,
        'annual_income', c.annual_income,
        'credit_tier_at_origination', c.credit_tier_at_origination,
        'credit_tier_now', c.credit_tier_now,
        'other_monthly_debt', c.other_monthly_debt,
        'tenure_months_with_tfs', c.tenure_months_with_tfs,
        'autopay', c.autopay,
        'digital_engagement', c.digital_engagement,
        'preferred_channel', c.preferred_channel,
        'marketing_consent', c.marketing_consent,
        'vulnerable_flag', c.vulnerable_flag,
        'payment_to_income_pct', c.payment_to_income_pct,
        'debt_to_income_pct', c.debt_to_income_pct,
        'financial_stress_score', c.financial_stress_score
    ) AS customer,
    to_jsonb(v) - 'customer_id' AS vehicle,
    to_jsonb(a) - 'customer_id' AS account,
    jsonb_build_object(
        'situation_id', s.situation_id,
        'customer_says', s.customer_says,
        'context_summary', s.context_summary
    ) AS situation,
    COALESCE(
        (
            SELECT jsonb_agg(to_jsonb(o) - 'customer_id' ORDER BY o.option_id)
            FROM toyota.option_scenarios o
            WHERE o.customer_id = c.customer_id
        ),
        '[]'::jsonb
    ) AS options,
    to_jsonb(g) - 'customer_id' AS golden_answer
FROM toyota.customers c
LEFT JOIN toyota.vehicles v ON v.customer_id = c.customer_id
LEFT JOIN toyota.accounts a ON a.customer_id = c.customer_id
LEFT JOIN toyota.situations s ON s.customer_id = c.customer_id
LEFT JOIN toyota.golden_answers g ON g.customer_id = c.customer_id;
"""


CATALOG_ROWS = [
    (
        "toyota.customers",
        "toyota",
        "customers",
        "data/customers.csv",
        "20 DFW synthetic TFS customers",
        True,
        None,
    ),
    (
        "toyota.vehicles",
        "toyota",
        "vehicles",
        "data/vehicles.csv",
        "One Toyota vehicle per customer",
        True,
        None,
    ),
    (
        "toyota.accounts",
        "toyota",
        "accounts",
        "data/accounts.csv",
        "15 loans + 5 leases",
        True,
        None,
    ),
    (
        "toyota.situations",
        "toyota",
        "situations",
        "data/situations.csv",
        "Customer 'today' prompts",
        True,
        None,
    ),
    (
        "toyota.option_scenarios",
        "toyota",
        "option_scenarios",
        "data/option_scenarios.csv",
        "Precomputed next-move options",
        True,
        None,
    ),
    (
        "toyota.offers_catalog",
        "toyota",
        "offers_catalog",
        "data/offers_catalog.csv",
        "Offer catalog with eligibility",
        True,
        None,
    ),
    (
        "toyota.rate_sheet",
        "toyota",
        "rate_sheet",
        "data/rate_sheet.csv",
        "Synthetic APR by tier/term",
        True,
        None,
    ),
    (
        "toyota.value_drivers",
        "toyota",
        "value_drivers",
        "data/value_drivers.csv",
        "Business value assumptions",
        True,
        None,
    ),
    (
        "toyota.golden_answers",
        "toyota",
        "golden_answers",
        "data/golden_answers.csv",
        "Reference best next move per customer",
        True,
        None,
    ),
    (
        "toyota.customer_profiles",
        "toyota",
        "customer_profiles",
        "data/customer_profiles.json",
        "Joined customer profile view (JSON equivalent)",
        True,
        "Loaded as VIEW over normalized tables; JSON file not duplicated",
    ),
    (
        "finance.monthly_snapshots",
        "finance",
        "monthly_snapshots",
        "data/personal_finance_tracker_dataset.csv",
        "500-user monthly personal finance snapshots (hypertable)",
        True,
        None,
    ),
    (
        "source.xlsx_pack",
        "toyota",
        None,
        "data/toyota_next_move_data_pack.xlsx",
        "Workbook mirror of Toyota CSVs",
        False,
        "Not loaded; same content as toyota.* CSV tables",
    ),
]


def copy_df(cur, table: str, df: pd.DataFrame) -> int:
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    cols = sql.SQL(", ").join(map(sql.Identifier, df.columns.tolist()))
    schema, name = table.split(".", 1)
    copy_sql = sql.SQL("COPY {}.{} ({}) FROM STDIN WITH (FORMAT csv, NULL '\\N')").format(
        sql.Identifier(schema),
        sql.Identifier(name),
        cols,
    )
    cur.copy_expert(copy_sql.as_string(cur), buf)
    return len(df)


def load_toyota(cur) -> dict[str, int]:
    counts: dict[str, int] = {}

    customers = pd.read_csv(DATA / "customers.csv")
    customers["autopay"] = yn_to_bool(customers["autopay"])
    customers["marketing_consent"] = yn_to_bool(customers["marketing_consent"])
    customers["vulnerable_flag"] = yn_to_bool(customers["vulnerable_flag"])
    counts["toyota.customers"] = copy_df(cur, "toyota.customers", customers)

    vehicles = pd.read_csv(DATA / "vehicles.csv")
    vehicles["open_recall"] = yn_to_bool(vehicles["open_recall"])
    counts["toyota.vehicles"] = copy_df(cur, "toyota.vehicles", vehicles)

    accounts = pd.read_csv(DATA / "accounts.csv")
    accounts["autopay"] = yn_to_bool(accounts["autopay"])
    for col in ("mileage_allowance_total",):
        accounts[col] = pd.to_numeric(accounts[col], errors="coerce").astype("Int64")
    counts["toyota.accounts"] = copy_df(cur, "toyota.accounts", accounts)

    situations = pd.read_csv(DATA / "situations.csv")
    counts["toyota.situations"] = copy_df(cur, "toyota.situations", situations)

    offers = pd.read_csv(DATA / "offers_catalog.csv")
    counts["toyota.offers_catalog"] = copy_df(cur, "toyota.offers_catalog", offers)

    rates = pd.read_csv(DATA / "rate_sheet.csv")
    counts["toyota.rate_sheet"] = copy_df(cur, "toyota.rate_sheet", rates)

    drivers = pd.read_csv(DATA / "value_drivers.csv")
    counts["toyota.value_drivers"] = copy_df(cur, "toyota.value_drivers", drivers)

    options = pd.read_csv(DATA / "option_scenarios.csv")
    counts["toyota.option_scenarios"] = copy_df(cur, "toyota.option_scenarios", options)

    golden = pd.read_csv(DATA / "golden_answers.csv")
    counts["toyota.golden_answers"] = copy_df(cur, "toyota.golden_answers", golden)

    return counts


def load_finance(cur) -> dict[str, int]:
    df = pd.read_csv(DATA / "personal_finance_tracker_dataset.csv")
    df = df.rename(columns={"date": "snapshot_date"})
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"], utc=True)
    # Ensure column order matches table
    cols = [
        "snapshot_date",
        "user_id",
        "monthly_income",
        "income_volatility_3m",
        "income_growth_6m",
        "pay_frequency",
        "months_employed",
        "checking_balance",
        "available_balance",
        "overdraft_count_90d",
        "recurring_bill_total",
        "savings_balance",
        "savings_apy",
        "emergency_fund_months",
        "monthly_savings_contribution",
        "total_debt_balance",
        "weighted_avg_apr",
        "minimum_debt_payment",
        "remaining_loan_term_months",
        "credit_limit_total",
        "credit_utilization",
        "credit_card_apr",
        "late_payments_12m",
        "home_value",
        "mortgage_balance",
        "mortgage_interest_rate",
        "home_equity",
        "portfolio_value",
        "equity_allocation_pct",
        "retirement_contribution",
        "investment_volatility",
        "subscription_cost_monthly",
        "spending_volatility_3m",
        "budget_variance_pct",
        "savings_streak_months",
        "unusual_merchant_flag",
        "transaction_amount_zscore",
        "transaction_velocity_24h",
        "merchant_category_change",
        "liquidity_runway_months",
        "projected_balance_30d",
        "debt_service_coverage",
        "bill_payment_delay_count",
        "life_event_type",
    ]
    df = df[cols]
    return {"finance.monthly_snapshots": copy_df(cur, "finance.monthly_snapshots", df)}


def load_catalog(cur) -> None:
    cur.executemany(
        """
        INSERT INTO meta.dataset_catalog (
            dataset_key, schema_name, table_name, source_file,
            description, loaded_as_table, notes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        CATALOG_ROWS,
    )


def main() -> int:
    print(f"Connecting to Tiger service {SERVICE_ID}...")
    uri = tiger_uri()
    conn = psycopg2.connect(uri)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            print("Applying schema DDL...")
            cur.execute(DDL)
            print("Loading Toyota pack...")
            toyota_counts = load_toyota(cur)
            print("Loading personal finance tracker...")
            finance_counts = load_finance(cur)
            print("Writing dataset catalog...")
            load_catalog(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    for name, n in {**toyota_counts, **finance_counts}.items():
        print(f"  {name}: {n} rows")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
