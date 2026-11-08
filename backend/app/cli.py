"""`pnc` command line. Run as `python -m app.cli ...` or, after `pip install -e .`, as `pnc ...`.

Every command prints JSON so it can be used in scripts and CI. Data-changing commands run as tracked jobs (idempotency + retry)."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import typer

from app.core.config import BACKEND_DIR, DEMO_PACKAGE_DIR

app = typer.Typer(help="FinPilot PNC backend operations", no_args_is_help=True)
data_app, seed_app, finance_app, ml_app, test_app, jobs_app = (typer.Typer(no_args_is_help=True) for _ in range(6))
app.add_typer(data_app, name="data", help="Bronze/Silver/Gold data pipeline")
app.add_typer(seed_app, name="seed", help="Deterministic demo data")
app.add_typer(finance_app, name="finance", help="Finance engine")
app.add_typer(ml_app, name="ml", help="Model training and evaluation")
app.add_typer(test_app, name="test", help="Test suites")
app.add_typer(jobs_app, name="jobs", help="Background job status")


def out(obj) -> None:
    typer.echo(json.dumps(obj, indent=2, default=str))


def _fail(msg: str, code: int = 1):
    typer.echo(json.dumps({"ok": False, "error": msg}), err=True)
    raise typer.Exit(code)


# ------------------------------------------------------------------------------------------------ data
@data_app.command("validate")
def data_validate(package_dir: Path = typer.Option(DEMO_PACKAGE_DIR, help="Folder with the four CSV files")):
    """Validate a package against the contract WITHOUT touching the database."""
    import pandas as pd

    from app.pnc.data import pipeline as P

    if not package_dir.exists():
        _fail(f"package folder not found: {package_dir}")
    report: dict = {"package_dir": str(package_dir), "datasets": {}}
    frames = {}
    for fname, table in P.DATASETS:
        path = package_dir / fname
        if not path.exists():
            _fail(f"missing file {fname}")
        df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
        if "source_type" not in df:
            df["source_type"] = "unknown"
        try:
            good, bad = P.validate_frame(df, P.SCHEMAS[table])
        except ValueError as exc:
            _fail(f"{fname}: {exc}")
        frames[table] = good
        report["datasets"][table] = {"rows": len(df), "valid": len(good), "invalid": len(bad), "first_failures": bad[:5]}
    c, a, t, s = (frames[k] for k in ("pnc_customers", "pnc_accounts", "pnc_transactions", "pnc_monthly_statements"))
    contract = {
        "customers_30": len(c) == 30, "accounts_196": len(a) == 196, "account_types_8": a["account_type"].nunique() == 8,
        "statements_4704": len(s) == 4704, "months_24": s["statement_month"].nunique() == 24,
        "customer_ids_C001_C030": set(c["customer_id"]) == {f"C{i:03d}" for i in range(1, 31)},
        "no_merchant_field": "merchant" not in t.columns,
        "transactions_21225_sponsor_contract": len(t) == 21225,
    }
    report["contract_checks"] = contract
    report["transactions"] = {"rows": len(t), "note": "The sponsor contract states 21,225; the labeled demo package may differ (see Skill.md)."}
    report["ok"] = all(v for k, v in contract.items() if k != "transactions_21225_sponsor_contract") and \
        all(d["invalid"] == 0 for d in report["datasets"].values())
    out(report)
    raise typer.Exit(0 if report["ok"] else 1)


@data_app.command("ingest")
def data_ingest(package_dir: Path = typer.Option(DEMO_PACKAGE_DIR), force: bool = False):
    """Bronze + Silver load. Re-running with unchanged files is a no-op."""
    from app.pnc import jobs
    from app.pnc.data import pipeline as P
    key = f"data.ingest:{P.dataset_version(package_dir)}"
    out(jobs.run_job("data.ingest", lambda: P.ingest(package_dir, force=force), idempotency_key=key, force=force))


@data_app.command("reconcile")
def data_reconcile():
    """Run the accounting reconciliation checks. Exit code 1 if any check fails."""
    from app.pnc.data import pipeline as P
    rec = P.reconcile()
    out(rec)
    raise typer.Exit(0 if all(c["passed"] for c in rec["checks"]) else 1)


@data_app.command("build-features")
def data_build_features(as_of: str = typer.Option("2026-10-31")):
    """Gold tables and per-customer health snapshots (idempotent)."""
    from app.pnc import jobs
    from app.pnc.data import pipeline as P
    from app.pnc.features import health_snapshots
    d = date.fromisoformat(as_of)
    out(jobs.run_job("data.build_features", lambda: {"gold": P.build_gold(), "snapshots": health_snapshots.build_snapshots(d)},
                     idempotency_key=f"data.build_features:{as_of}", force=True))


@data_app.command("status")
def data_status():
    """Row counts and the latest bronze ingestions."""
    from sqlalchemy import text

    from app.core.db import db_session
    tables = ["pnc_customers", "pnc_accounts", "pnc_transactions", "pnc_monthly_statements", "pnc_balance_history", "pnc_income_history",
              "pnc_recurring_obligations", "pnc_health_snapshots", "pnc_fraud_events", "pnc_savings_goals", "silver_quarantine"]
    with db_session() as s:
        counts = {t: s.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in tables}
        ing = [dict(r) for r in s.execute(text("SELECT dataset_name, status, record_count, quarantined_count, dataset_version, source_type, ingested_at "
                                               "FROM bronze_ingestions ORDER BY ingested_at DESC LIMIT 8")).mappings()]
    out({"counts": counts, "ingestions": ing})


# ------------------------------------------------------------------------------------------------ seed
@seed_app.command("demo-data")
def seed_demo_data(out_dir: Path = typer.Option(DEMO_PACKAGE_DIR)):
    """(Re)generate the labeled demo package (seeds 20261107 / 20261108). Deterministic."""
    from app.pnc.data.generator import generate
    m = generate(out_dir)
    out({k: m[k] for k in m if k in ("source_type", "snapshot_seed", "history_seed", "counts", "dataset_label")} or m)


@seed_app.command("users")
def seed_users(password: str = typer.Option("demo", help="Shared demo password for every seeded user")):
    """Create/refresh app_users for every customer + employee, with Skill.md role → tabs mapping."""
    from app.pnc.auth_users import seed_users as _seed
    out(_seed(password))


# ------------------------------------------------------------------------------------------------ finance
@finance_app.command("verify")
def finance_verify():
    """Run the finance-engine tests (known values, property tests)."""
    raise typer.Exit(_pytest("tests/test_finance_engine.py"))


def _xray_for(customer: str, as_of: str):
    from app.core.db import SessionContext, db_session
    from app.pnc.features.snapshot import load_snapshot
    d = date.fromisoformat(as_of)
    with db_session(SessionContext(role="customer", actor_id=customer, customer_id=customer)) as c:
        return c, load_snapshot(c, customer, d)


@finance_app.command("calculate-indicators")
def finance_indicators(customer: str = typer.Argument(..., help="e.g. C001"), as_of: str = "2026-10-31"):
    """Compute the health indicators for one customer, through the customer role (RLS applies)."""
    from app.core.db import SessionContext, db_session
    from app.pnc.features.snapshot import load_snapshot
    from app.pnc.features.xray import build_xray
    with db_session(SessionContext(role="customer", actor_id=customer, customer_id=customer)) as c:
        out(build_xray(load_snapshot(c, customer, date.fromisoformat(as_of))))


@finance_app.command("forecast")
def finance_forecast(customer: str = typer.Argument(...), months: int = 3):
    """Cash-flow forecast from the offline-selected model (needs `pnc ml train-cashflow` first)."""
    from app.core.db import SessionContext, db_session
    from app.pnc.errors import Unavailable
    from app.pnc.features.snapshot import load_snapshot
    from app.pnc.ml import cashflow
    with db_session(SessionContext(role="customer", actor_id=customer, customer_id=customer)) as c:
        s = load_snapshot(c, customer, date(2026, 10, 31))
    surplus = [float(a) - float(b) - float(d) for a, b, d in zip(s.monthly["income"], s.monthly["consumption_spending"], s.monthly["debt_payments"])]
    try:
        out(cashflow.forecast_from_series(surplus, months))
    except (Unavailable, ValueError) as exc:
        _fail(str(exc))


@finance_app.command("run-scenario")
def finance_scenario(customer: str = typer.Argument(...), price: float = 30000, down_payment: float = 5000, apr_pct: float = 7.0, term_months: int = 60):
    """FutureYou purchase scenario against the baseline (typed evidence)."""
    from decimal import Decimal as D

    from app.core.db import SessionContext, db_session
    from app.pnc.features import futureyou as fy
    from app.pnc.features.snapshot import load_snapshot
    with db_session(SessionContext(role="customer", actor_id=customer, customer_id=customer)) as c:
        s = load_snapshot(c, customer, date(2026, 10, 31))
    spec = fy.ScenarioSpec(label="CLI purchase", purchase=fy.PurchaseSpec(price=D(str(price)), down_payment=D(str(down_payment)),
                                                                          apr_pct=D(str(apr_pct)), term_months=term_months))
    out({"baseline": fy.project(s, fy.ScenarioSpec(label="Baseline")).model_dump(mode="json"), "scenario": fy.project(s, spec).model_dump(mode="json")})


# ------------------------------------------------------------------------------------------------ ml
@ml_app.command("train-cashflow")
def ml_train_cashflow():
    """Rolling-origin backtest of baselines vs LightGBM; writes the report and logs to MLflow."""
    from app.pnc import jobs
    from app.pnc.ml import cashflow
    out(jobs.run_job("ml.train_cashflow", cashflow.train_and_log))


@ml_app.command("train-anomalies")
def ml_train_anomalies():
    """Isolation Forest vs rules on spending; evaluated ONLY on synthetic injected anomalies."""
    from app.pnc import jobs
    from app.pnc.ml import anomaly
    out(jobs.run_job("ml.train_anomalies", anomaly.train_and_log))


@ml_app.command("evaluate")
def ml_evaluate():
    """Print the latest stored evaluation reports (no retraining)."""
    from app.pnc.ml.tracking import artifact_dir
    reports = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(artifact_dir().glob("*.json"))}
    if not reports:
        _fail("no reports found; run `pnc ml train-cashflow` and `pnc ml train-anomalies`")
    out(reports)


# ------------------------------------------------------------------------------------------------ jobs / test
@jobs_app.command("list")
def jobs_list(limit: int = 20):
    from app.pnc import jobs
    out(jobs.list_jobs(limit))


def _pytest(*targets: str, extra: list[str] | None = None) -> int:
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *(targets or ["tests"]), *(extra or [])]
    return subprocess.call(cmd, cwd=BACKEND_DIR, env={**__import__("os").environ, "PYTHONPATH": str(BACKEND_DIR)})


@test_app.command("all")
def test_all(write_tests: bool = typer.Option(False, help="Also run the opt-in DB write/concurrency tests")):
    """Run the full test suite."""
    import os
    if write_tests:
        os.environ["RUN_DB_WRITE_TESTS"] = "1"
    raise typer.Exit(_pytest("tests"))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
