"""Bronze -> Silver -> Gold pipelines for the PNC data package. Idempotent, quarantine-based, no silent repair.

Bronze  : file hash + metadata recorded in ``bronze_ingestions`` (raw files are never modified).
Silver  : Pandera validation; failing rows go to ``silver_quarantine`` with the reason and are NOT loaded.
Gold    : balance history, income history, recurring obligations (+ SQL views for cash-flow summaries).
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pandas as pd
import pandera.pandas as pa
from sqlalchemy import text

from app.core.config import DEMO_PACKAGE_DIR
from app.core.db import db_session

SCHEMA_VERSION = "pnc-contract-1"
WINDOW_START, WINDOW_END = pd.Timestamp("2024-11-01"), pd.Timestamp("2026-10-31")
ACCOUNT_TYPES = ["checking", "savings", "cd", "ira", "credit_card", "auto_loan", "personal_loan", "mortgage"]
FLOW_CLASSES = ["income", "expense", "internal_transfer", "external_transfer", "non_cash"]

DATASETS: list[tuple[str, str]] = [
    ("profiles.csv", "pnc_customers"), ("accounts.csv", "pnc_accounts"),
    ("transactions.csv", "pnc_transactions"), ("monthly_statements.csv", "pnc_monthly_statements"),
]

COLUMNS = {
    "pnc_customers": ["customer_id", "display_name", "age", "city", "pay_frequency", "annual_income",
                      "income_sources_count", "credit_score", "essential_spending_ratio", "savings_rate_assumption",
                      "marketing_consent", "vulnerable_flag", "preferred_channel", "dataset_version", "source_type"],
    "pnc_accounts": ["account_id", "customer_id", "account_type", "name", "opened_date", "balance", "apy_pct", "apr_pct",
                     "credit_limit", "original_principal", "term_months", "required_monthly_payment", "maturity_date",
                     "dataset_version", "source_type"],
    "pnc_transactions": ["transaction_id", "posted_date", "customer_id", "account_id", "account_type", "transaction_type",
                         "category", "description", "amount", "balance_change", "balance_after", "flow_class",
                         "transfer_id", "source_type"],
    "pnc_monthly_statements": ["account_id", "statement_month", "customer_id", "opening_balance", "closing_balance",
                               "total_increases", "total_decreases", "transaction_count", "source_type"],
}
INT_COLUMNS = {"age", "income_sources_count", "credit_score", "term_months", "transaction_count"}
CONFLICT = {
    "pnc_customers": "(customer_id)", "pnc_accounts": "(account_id)",
    "pnc_transactions": "(transaction_id, posted_date)", "pnc_monthly_statements": "(account_id, statement_month)",
}

_bool = pa.Column(bool, coerce=True)
SCHEMAS: dict[str, pa.DataFrameSchema] = {
    "pnc_customers": pa.DataFrameSchema({
        "customer_id": pa.Column(str, pa.Check.str_matches(r"^C\d{3}$")),
        "display_name": pa.Column(str),
        "age": pa.Column(int, pa.Check.in_range(18, 100), coerce=True, nullable=True),
        "pay_frequency": pa.Column(str, pa.Check.isin(["weekly", "biweekly", "semimonthly", "monthly"])),
        "annual_income": pa.Column(float, pa.Check.gt(0), coerce=True),
        "income_sources_count": pa.Column(int, pa.Check.ge(1), coerce=True),
        "credit_score": pa.Column(int, pa.Check.in_range(300, 850), coerce=True, nullable=True),
        "marketing_consent": _bool, "vulnerable_flag": _bool,
        "preferred_channel": pa.Column(str, pa.Check.isin(["email", "sms", "phone", "mail", "none"]), nullable=True),
    }, strict=False),
    "pnc_accounts": pa.DataFrameSchema({
        "account_id": pa.Column(str, pa.Check.str_matches(r"^A\d{4}$")),
        "customer_id": pa.Column(str),
        "account_type": pa.Column(str, pa.Check.isin(ACCOUNT_TYPES)),
        "balance": pa.Column(float, pa.Check.ge(0), coerce=True),
        "apr_pct": pa.Column(float, pa.Check.in_range(0, 40), coerce=True, nullable=True),
        "apy_pct": pa.Column(float, pa.Check.in_range(0, 20), coerce=True, nullable=True),
    }, strict=False),
    "pnc_transactions": pa.DataFrameSchema({
        "transaction_id": pa.Column(str),
        "posted_date": pa.Column("datetime64[ns]", pa.Check.in_range(WINDOW_START, WINDOW_END), coerce=True),
        "amount": pa.Column(float, pa.Check.ge(0), coerce=True),
        "balance_change": pa.Column(float, coerce=True),
        "balance_after": pa.Column(float, coerce=True),
        "flow_class": pa.Column(str, pa.Check.isin(FLOW_CLASSES)),
        "account_type": pa.Column(str, pa.Check.isin(ACCOUNT_TYPES)),
    }, strict=False, checks=[
        pa.Check(lambda d: (d["amount"] - d["balance_change"].abs()).abs() < 0.005, error="amount != |balance_change|"),
    ]),
    "pnc_monthly_statements": pa.DataFrameSchema({
        "account_id": pa.Column(str),
        "statement_month": pa.Column("datetime64[ns]", pa.Check.in_range(WINDOW_START, WINDOW_END), coerce=True),
        "opening_balance": pa.Column(float, coerce=True), "closing_balance": pa.Column(float, coerce=True),
        "total_increases": pa.Column(float, pa.Check.ge(0), coerce=True),
        "total_decreases": pa.Column(float, pa.Check.ge(0), coerce=True),
    }, strict=False, checks=[
        pa.Check(lambda d: (d["opening_balance"] + d["total_increases"] - d["total_decreases"] - d["closing_balance"]).abs() < 0.005,
                 error="statement does not reconcile (opening + increases - decreases != closing)"),
    ]),
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dataset_version(package_dir: Path) -> str:
    h = hashlib.sha256()
    for name, _ in DATASETS:
        h.update(sha256_file(package_dir / name).encode())
    return h.hexdigest()[:12]


def validate_frame(df: pd.DataFrame, schema: pa.DataFrameSchema) -> tuple[pd.DataFrame, list[tuple[int, str]]]:
    """Return (valid rows, [(row_index, reason)]). Invalid rows are never repaired."""
    try:
        return schema.validate(df, lazy=True), []
    except pa.errors.SchemaErrors as exc:
        fc = exc.failure_cases
        bad: dict[int, str] = {}
        schema_level = fc[fc["index"].isna()]
        if len(schema_level):  # column-level/structural failure: nothing can be trusted
            raise ValueError(f"structural schema failure: {schema_level[['column', 'check']].to_dict('records')}") from exc
        for idx, grp in fc.groupby("index"):
            bad[int(idx)] = "; ".join(sorted({f"{r.column}: {r.check}" for r in grp.itertuples()}))
        good = df.drop(index=list(bad.keys()))
        good, _ = (schema.validate(good, lazy=True), [])
        return good, sorted(bad.items())


def _copy_upsert(conn, table: str, df: pd.DataFrame) -> int:
    """COPY into a temp table, then INSERT .. ON CONFLICT DO NOTHING; returns rows inserted."""
    cols = COLUMNS[table]
    raw = conn.connection.driver_connection
    buf = io.StringIO()
    out = df[cols].copy()
    for c in INT_COLUMNS & set(cols):  # CSV round-trips can render integers as "12.0"; cast explicitly, never guess
        out[c] = pd.to_numeric(out[c]).astype("Int64")
    out.to_csv(buf, index=False, header=False, na_rep="")
    buf.seek(0)
    stage = f"stage_{table}"
    with raw.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE {stage} (LIKE finpilot.{table} INCLUDING DEFAULTS) ON COMMIT DROP")
        with cur.copy(f"COPY {stage} ({', '.join(cols)}) FROM STDIN WITH (FORMAT csv, NULL '')") as cp:
            cp.write(buf.read())
        key = {c.strip() for c in CONFLICT[table].strip("()").split(",")}
        if table in ("pnc_customers", "pnc_accounts"):   # dimension rows: a changed file updates them in place
            sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in key)
            action = f"DO UPDATE SET {sets}"
        else:                                           # ledger rows are append-only: duplicates are ignored
            action = "DO NOTHING"
        cur.execute(f"INSERT INTO finpilot.{table} ({', '.join(cols)}) SELECT {', '.join(cols)} FROM {stage} "
                    f"ON CONFLICT {CONFLICT[table]} {action}")
        return cur.rowcount


def reset_ledger() -> dict:
    """Explicitly empty the PNC ledger and derived tables (customers/accounts are upserted, never deleted).

    Used only when the source package changed (e.g. the demo generator was recalibrated). Records what it removed.
    """
    tables = ["pnc_transactions", "pnc_monthly_statements", "pnc_balance_history", "pnc_income_history",
              "pnc_recurring_obligations", "pnc_health_snapshots", "pnc_forecast_results", "pnc_fraud_events"]
    removed = {}
    with db_session() as s:
        for t in tables:
            removed[t] = s.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
            s.execute(text(f"TRUNCATE {t}"))
        s.execute(text("DELETE FROM bronze_ingestions WHERE dataset_name IN "
                       "('pnc_customers','pnc_accounts','pnc_transactions','pnc_monthly_statements')"))
    return removed


def ingest(package_dir: Path | None = None, force: bool = False) -> dict:
    """Bronze + silver for all four datasets. Re-running with an unchanged file is a no-op (idempotent)."""
    package_dir = Path(package_dir or DEMO_PACKAGE_DIR)
    manifest_path = package_dir / "history_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    source_type = manifest.get("source_type", "sponsor_lab_package")
    version = dataset_version(package_dir)
    report: dict = {"dataset_version": version, "source_type": source_type, "datasets": {}}
    accepted_ids: dict[str, set] = {}

    for fname, table in DATASETS:
        path = package_dir / fname
        digest = sha256_file(path)
        df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
        with db_session() as s:
            prior = s.execute(text("SELECT status, ingestion_id FROM bronze_ingestions WHERE dataset_name=:d AND file_sha256=:h"),
                              {"d": table, "h": digest}).first()
            if prior and prior.status == "succeeded" and not force:
                report["datasets"][table] = {"status": "skipped_duplicate", "rows": len(df)}
                accepted_ids[table] = set()
                continue
            if prior:
                s.execute(text("DELETE FROM bronze_ingestions WHERE ingestion_id=:i"), {"i": prior.ingestion_id})
            ing_id = s.execute(text(
                "INSERT INTO bronze_ingestions(dataset_name, source_path, file_sha256, source_type, schema_version, "
                "dataset_version, record_count, status) VALUES (:d,:p,:h,:st,:sv,:dv,:n,'started') RETURNING ingestion_id"),
                {"d": table, "p": str(path), "h": digest, "st": source_type, "sv": SCHEMA_VERSION, "dv": version,
                 "n": len(df)}).scalar_one()
        try:
            typed = df.copy()
            typed["dataset_version"] = version
            if "source_type" not in typed:
                typed["source_type"] = source_type
            good, bad = validate_frame(typed, SCHEMAS[table])
            # referential checks are quarantine reasons too (no orphan rows loaded)
            with db_session() as s:
                if table == "pnc_accounts":
                    known = {r[0] for r in s.execute(text("SELECT customer_id FROM pnc_customers"))}
                    mask = ~good["customer_id"].isin(known)
                elif table in ("pnc_transactions", "pnc_monthly_statements"):
                    known = {r[0] for r in s.execute(text("SELECT account_id FROM pnc_accounts"))}
                    mask = ~good["account_id"].isin(known)
                else:
                    mask = pd.Series(False, index=good.index)
                for idx in good.index[mask]:
                    bad.append((int(idx), "referential: parent row missing"))
                good = good[~mask]
                for idx, reason in bad:
                    s.execute(text("INSERT INTO silver_quarantine(ingestion_id, dataset_name, row_number, reason, raw) "
                                   "VALUES (:i,:d,:r,:why,CAST(:raw AS jsonb))"),
                              {"i": ing_id, "d": table, "r": idx + 2, "why": reason[:500],
                               "raw": json.dumps({k: (None if pd.isna(v) else v) for k, v in df.loc[idx].items()})})
                inserted = _copy_upsert(s, table, good) if len(good) else 0
                s.execute(text("UPDATE bronze_ingestions SET status='succeeded', quarantined_count=:q WHERE ingestion_id=:i"),
                          {"q": len(bad), "i": ing_id})
            report["datasets"][table] = {"status": "succeeded", "rows": len(df), "inserted": inserted, "quarantined": len(bad)}
        except Exception as exc:  # recorded, then re-raised: failures are never hidden
            with db_session() as s:
                s.execute(text("UPDATE bronze_ingestions SET status='failed', error=:e WHERE ingestion_id=:i"),
                          {"e": str(exc)[:1000], "i": ing_id})
            raise
    return report


# --------------------------------------------------------------------------------------- reconciliation
def reconcile() -> dict:
    """Run the accounting checks against the loaded tables. Every check reports pass/fail and evidence."""
    checks: list[dict] = []

    def add(name: str, ok: bool, detail) -> None:
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    with db_session() as s:
        q = lambda sql: s.execute(text(sql)).all()  # noqa: E731
        n_c = q("SELECT count(*) FROM pnc_customers")[0][0]
        n_a = q("SELECT count(*) FROM pnc_accounts")[0][0]
        n_t = q("SELECT count(*) FROM pnc_transactions")[0][0]
        n_s = q("SELECT count(*) FROM pnc_monthly_statements")[0][0]
        types = {r[0]: r[1] for r in q("SELECT account_type, count(*) FROM pnc_accounts GROUP BY 1")}
        add("customers == 30", n_c == 30, n_c)
        add("accounts == 196", n_a == 196, n_a)
        add("eight account types present", set(types) == set(ACCOUNT_TYPES), types)
        add("statements == accounts x 24 months (4704)", n_s == n_a * 24 == 4704, n_s)
        add("transactions loaded (count reported, sponsor figure 21,225 not reproducible)", n_t > 0, n_t)
        r = q("SELECT count(*) FROM pnc_transactions WHERE amount <> abs(balance_change)")[0][0]
        add("amount == |balance_change| for every transaction", r == 0, r)
        r = q("""SELECT count(*) FROM (
                   SELECT account_id, balance_after - (lag(balance_after) OVER w + balance_change) AS drift
                     FROM pnc_transactions WINDOW w AS (PARTITION BY account_id ORDER BY posted_date, transaction_id)) x
                  WHERE drift IS NOT NULL AND abs(drift) > 0.005""")[0][0]
        add("running balance continuity per account", r == 0, r)
        r = q("""SELECT count(*) FROM pnc_monthly_statements m JOIN LATERAL (
                   SELECT coalesce(sum(amount) FILTER (WHERE balance_change > 0),0) inc,
                          coalesce(sum(amount) FILTER (WHERE balance_change < 0),0) dec, count(*) n
                     FROM pnc_transactions t WHERE t.account_id = m.account_id
                      AND t.posted_date >= m.statement_month AND t.posted_date < (m.statement_month + INTERVAL '1 month')) t ON true
                  WHERE abs(t.inc - m.total_increases) > 0.005 OR abs(t.dec - m.total_decreases) > 0.005 OR t.n <> m.transaction_count""")[0][0]
        add("statement totals equal transaction sums", r == 0, r)
        r = q("""SELECT count(*) FROM (SELECT opening_balance - lag(closing_balance) OVER (PARTITION BY account_id ORDER BY statement_month) AS gap
                   FROM pnc_monthly_statements) x WHERE gap IS NOT NULL AND abs(gap) > 0.005""")[0][0]
        add("statement opening == previous closing", r == 0, r)
        r = q("""SELECT count(*) FROM pnc_accounts a JOIN LATERAL (SELECT closing_balance FROM pnc_monthly_statements m
                   WHERE m.account_id = a.account_id ORDER BY statement_month DESC LIMIT 1) m ON true
                  WHERE abs(a.balance - m.closing_balance) > 0.005""")[0][0]
        add("account balance == latest statement closing", r == 0, r)
        r = q("""SELECT count(*) FROM pnc_accounts a JOIN LATERAL (SELECT balance_after FROM pnc_transactions t
                   WHERE t.account_id = a.account_id ORDER BY posted_date DESC, transaction_id DESC LIMIT 1) t ON true
                  WHERE abs(a.balance - t.balance_after) > 0.005""")[0][0]
        add("account balance == last transaction balance_after", r == 0, r)
        r = q("""SELECT count(*) FROM (SELECT transfer_id FROM pnc_transactions WHERE flow_class='internal_transfer'
                   GROUP BY transfer_id HAVING count(*) <> 2 OR sum(balance_change) FILTER (WHERE account_type IN ('checking','savings','cd','ira')) <> 0
                      OR count(DISTINCT posted_date) <> 1) x""")[0][0]
        add("internal transfers are paired, offsetting, same-day", r == 0, r)
        r = q("""SELECT count(*) FROM (SELECT transfer_id FROM pnc_transactions WHERE transfer_id LIKE 'X%' AND flow_class IN ('expense','non_cash')
                   GROUP BY transfer_id HAVING count(*) <> 2 OR count(DISTINCT amount) <> 1) x""")[0][0]
        add("debt payments: one cash leg + one non-cash leg of equal amount (counted once)", r == 0, r)
        r = q("SELECT count(*) FROM pnc_transactions WHERE flow_class IN ('internal_transfer','non_cash') AND category LIKE 'debt_payment%'")[0][0]
        add("debt-payment cash leg is never classed as a transfer", r == 0, r)
        r = q("SELECT count(*) FROM pnc_accounts WHERE account_type='credit_card' AND balance > credit_limit")[0][0]
        add("card balances within limit", r == 0, r)
        r = q("SELECT count(*) FROM pnc_accounts WHERE balance < 0")[0][0]
        add("positive balances for assets and liabilities", r == 0, r)
        lo, hi = q("SELECT min(posted_date), max(posted_date) FROM pnc_transactions")[0]
        add("observation window 2024-11-01..2026-10-31", str(lo) >= "2024-11-01" and str(hi) <= "2026-10-31", [str(lo), str(hi)])
        r = q("""SELECT count(*) FROM information_schema.columns WHERE table_schema='finpilot' AND table_name='pnc_transactions'
                  AND column_name ILIKE '%merchant%'""")[0][0]
        add("no merchant field in canonical transactions", r == 0, r)
        r = q("SELECT count(DISTINCT source_type) FROM pnc_transactions")[0][0]
        add("single source_type labelled", r == 1, r)
    return {"passed": all(c["passed"] for c in checks), "checks": checks}


# --------------------------------------------------------------------------------------------- gold
def build_gold() -> dict:
    """Idempotently (re)build gold tables: balance history, income history, recurring obligations."""
    with db_session() as s:
        s.execute(text("""
            INSERT INTO pnc_balance_history(account_id, as_of, customer_id, account_type, balance)
            SELECT m.account_id, (m.statement_month + INTERVAL '1 month' - INTERVAL '1 day')::date, m.customer_id,
                   a.account_type, m.closing_balance
              FROM pnc_monthly_statements m JOIN pnc_accounts a USING (account_id)
            ON CONFLICT (account_id, as_of) DO NOTHING"""))
        s.execute(text("""
            INSERT INTO pnc_income_history(customer_id, month, income)
            SELECT c.customer_id, gs::date, coalesce(sum(t.amount), 0)
              FROM pnc_customers c CROSS JOIN generate_series('2024-11-01'::date, '2026-10-01'::date, INTERVAL '1 month') gs
              LEFT JOIN pnc_transactions t ON t.customer_id = c.customer_id AND t.flow_class = 'income'
               AND t.posted_date >= gs AND t.posted_date < gs + INTERVAL '1 month'
             GROUP BY c.customer_id, gs
            ON CONFLICT (customer_id, month) DO NOTHING"""))
        s.execute(text("DELETE FROM pnc_recurring_obligations"))
        # loan obligations come from account terms; card minimums use the documented assumption max($25, 2% of balance)
        s.execute(text("""
            INSERT INTO pnc_recurring_obligations(obligation_id, customer_id, account_id, kind, monthly_amount, due_day, origin, evidence)
            SELECT 'OBL-' || account_id, customer_id, account_id, 'debt_payment', required_monthly_payment, 5, 'account_terms',
                   jsonb_build_object('source','accounts.required_monthly_payment')
              FROM pnc_accounts WHERE required_monthly_payment IS NOT NULL AND balance > 0"""))
        s.execute(text("""
            INSERT INTO pnc_recurring_obligations(obligation_id, customer_id, account_id, kind, monthly_amount, due_day, origin, evidence)
            SELECT 'OBL-' || account_id, customer_id, account_id, 'debt_payment', greatest(25, round(balance * 0.02, 2)), 20,
                   'synthetic_seed', jsonb_build_object('assumption','card minimum = max($25, 2% of balance)')
              FROM pnc_accounts WHERE account_type = 'credit_card' AND balance > 0"""))
        # recurring bills detected from transactions: same category+description in >= 6 of the last 12 months
        s.execute(text("""
            INSERT INTO pnc_recurring_obligations(obligation_id, customer_id, kind, monthly_amount, due_day, origin, evidence)
            SELECT 'DET-' || customer_id || '-' || md5(category || description), customer_id,
                   CASE WHEN category = 'rent' THEN 'housing' WHEN category IN ('utilities','telecom') THEN 'utility'
                        WHEN category = 'insurance' THEN 'insurance' WHEN category = 'subscriptions' THEN 'subscription' ELSE 'other' END,
                   round(avg(amount), 2), round(avg(extract(day FROM posted_date)))::int, 'detected_from_transactions',
                   jsonb_build_object('occurrences', count(*), 'months', count(DISTINCT date_trunc('month', posted_date)),
                                      'category', category, 'description', description)
              FROM pnc_transactions
             WHERE flow_class = 'expense' AND category IN ('rent','utilities','insurance','telecom','subscriptions')
               AND posted_date > DATE '2026-10-31' - INTERVAL '12 months'
             GROUP BY customer_id, category, description
            HAVING count(DISTINCT date_trunc('month', posted_date)) >= 6
               AND stddev_samp(amount) <= 0.15 * avg(amount)"""))
        counts = {t: s.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
                  for t in ("pnc_balance_history", "pnc_income_history", "pnc_recurring_obligations")}
        s.execute(text("""
            INSERT INTO feature_catalog(feature_name, layer, formula, source_columns, as_of_rule, version) VALUES
             ('gold_monthly_cashflow','derived','income/consumption/debt/savings per month from classified transactions',
              ARRAY['pnc_transactions.flow_class','category','amount'],'posted_date <= as_of','1'),
             ('pnc_balance_history','derived','statement closing balance at month end',
              ARRAY['pnc_monthly_statements.closing_balance'],'as_of <= as_of','1'),
             ('pnc_income_history','derived','sum of flow_class=income per month',
              ARRAY['pnc_transactions.amount'],'month <= as_of','1'),
             ('pnc_recurring_obligations','derived','account terms + detected recurrence (>=6 of 12 months, CV<=15%)',
              ARRAY['pnc_accounts','pnc_transactions'],'window ends at as_of','1')
            ON CONFLICT (feature_name, version) DO NOTHING"""))
    return counts
