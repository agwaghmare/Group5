"""
Load Group5 datasets into Tiger Cloud (TimescaleDB).

Org layout:
  pnc     - PNC customers from personal_finance_tracker_dataset.csv
  meta    - Dataset catalog / provenance
"""

from __future__ import annotations

import io
import subprocess
import sys
from datetime import date
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


DDL = """
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE SCHEMA IF NOT EXISTS pnc;
CREATE SCHEMA IF NOT EXISTS meta;

DROP TABLE IF EXISTS pnc.monthly_snapshots CASCADE;
DROP TABLE IF EXISTS pnc.customers CASCADE;
DROP TABLE IF EXISTS finance.monthly_snapshots CASCADE;
DROP SCHEMA IF EXISTS finance CASCADE;

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

-- ---------------------------------------------------------------------------
-- PNC customers (personal finance tracker)
-- ---------------------------------------------------------------------------
CREATE TABLE pnc.customers (
    customer_id                  BIGINT PRIMARY KEY,
    org                          TEXT NOT NULL DEFAULT 'pnc' CHECK (org = 'pnc'),
    pay_frequency                TEXT,
    months_employed              INTEGER,
    monthly_income               DOUBLE PRECISION,
    checking_balance             DOUBLE PRECISION,
    savings_balance              DOUBLE PRECISION,
    total_debt_balance           DOUBLE PRECISION,
    credit_utilization           DOUBLE PRECISION,
    emergency_fund_months        DOUBLE PRECISION,
    life_event_type              TEXT,
    as_of_snapshot_date          TIMESTAMPTZ NOT NULL,
    source_type                  TEXT NOT NULL DEFAULT 'synthetic_seed'
);

CREATE TABLE pnc.monthly_snapshots (
    snapshot_date                TIMESTAMPTZ NOT NULL,
    customer_id                  BIGINT NOT NULL REFERENCES pnc.customers (customer_id),
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
    PRIMARY KEY (customer_id, snapshot_date)
) WITH (
    tsdb.hypertable,
    tsdb.partition_column = 'snapshot_date',
    tsdb.segmentby = 'customer_id',
    tsdb.orderby = 'snapshot_date DESC',
    tsdb.chunk_interval = '1 month'
);

CREATE INDEX pnc_snapshots_date_idx ON pnc.monthly_snapshots (snapshot_date DESC);
"""


CATALOG_ROWS = [
    (
        "pnc.customers",
        "pnc",
        "customers",
        "data/personal_finance_tracker_dataset.csv",
        "PNC customer profiles derived from latest tracker snapshot (500 users)",
        True,
        "Lab_Package not used; tracker CSV is the PNC customer source",
    ),
    (
        "pnc.monthly_snapshots",
        "pnc",
        "monthly_snapshots",
        "data/personal_finance_tracker_dataset.csv",
        "Monthly personal-finance snapshots hypertable",
        True,
        None,
    ),
]


def copy_df(cur, table: str, df: pd.DataFrame) -> int:
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    cols = sql.SQL(", ").join(map(sql.Identifier, df.columns.tolist()))
    schema, name = table.split(".", 1)
    copy_sql = sql.SQL(
        "COPY {}.{} ({}) FROM STDIN WITH (FORMAT csv, NULL '\\N')"
    ).format(sql.Identifier(schema), sql.Identifier(name), cols)
    cur.copy_expert(copy_sql.as_string(cur), buf)
    return len(df)


def load_pnc(cur) -> dict[str, int]:
    raw = pd.read_csv(DATA / "personal_finance_tracker_dataset.csv")
    raw["snapshot_date"] = pd.to_datetime(raw["date"], utc=True)
    raw = raw.rename(columns={"user_id": "customer_id"})

    latest = (
        raw.sort_values("snapshot_date")
        .groupby("customer_id", as_index=False)
        .tail(1)
        .copy()
    )
    customers = latest[
        [
            "customer_id",
            "pay_frequency",
            "months_employed",
            "monthly_income",
            "checking_balance",
            "savings_balance",
            "total_debt_balance",
            "credit_utilization",
            "emergency_fund_months",
            "life_event_type",
            "snapshot_date",
        ]
    ].rename(columns={"snapshot_date": "as_of_snapshot_date"})
    customers.insert(1, "org", "pnc")
    customers["source_type"] = "synthetic_seed"
    n_cust = copy_df(cur, "pnc.customers", customers)

    snap_cols = [
        "snapshot_date",
        "customer_id",
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
    n_snap = copy_df(cur, "pnc.monthly_snapshots", raw[snap_cols])
    return {"pnc.customers": n_cust, "pnc.monthly_snapshots": n_snap}


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
            print("Applying schema DDL (pnc only)...")
            cur.execute(DDL)
            print("Loading PNC customers from finance tracker...")
            pnc_counts = load_pnc(cur)
            print("Writing dataset catalog...")
            load_catalog(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    for name, n in pnc_counts.items():
        print(f"  {name}: {n} rows")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
