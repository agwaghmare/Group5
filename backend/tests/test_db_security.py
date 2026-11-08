"""Database-enforced customer isolation (RLS + least-privilege role). Runs against the live TigerData service through the
real `app_customer` role; everything that writes runs in a transaction that is rolled back."""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.db

CUSTOMER_TABLES = ["pnc_customers", "pnc_accounts", "pnc_transactions", "pnc_monthly_statements", "pnc_balance_history",
                   "pnc_income_history", "pnc_recurring_obligations", "pnc_health_snapshots", "pnc_savings_goals", "pnc_fraud_events", "pnc_consents", "pnc_financial_scenarios", "pnc_fraud_cases"]


def sqlstate(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


@pytest.mark.parametrize("table", CUSTOMER_TABLES)
def test_customer_sees_only_own_rows(rollback_session, table):
    with rollback_session("customer", "C001", customer_id="C001") as c:
        owners = {r[0] for r in c.execute(text(f"SELECT DISTINCT customer_id FROM {table}"))}
        assert owners <= {"C001"}, (table, owners)


def test_customer_data_is_actually_visible_to_the_owner(rollback_session, q):
    with rollback_session("customer", "C001", customer_id="C001") as c:
        assert q(c, "SELECT count(*) FROM pnc_accounts")[0][0] > 0
        assert q(c, "SELECT count(*) FROM pnc_transactions")[0][0] > 0


def test_each_customer_sees_a_different_dataset(rollback_session, q):
    with rollback_session("customer", "C001", customer_id="C001") as c:
        a = {r[0] for r in q(c, "SELECT account_id FROM pnc_accounts")}
    with rollback_session("customer", "C002", customer_id="C002") as c:
        b = {r[0] for r in q(c, "SELECT account_id FROM pnc_accounts")}
    assert a and b and not (a & b)


def test_customer_with_no_context_sees_nothing(rollback_session, q):
    with rollback_session("customer", "", customer_id="") as c:
        assert q(c, "SELECT 1 FROM pnc_accounts LIMIT 1") == []


def test_customer_cannot_read_vulnerable_flag(rollback_session):
    with rollback_session("customer", "C001", customer_id="C001") as c:
        with pytest.raises(DBAPIError) as e:
            c.execute(text("SELECT vulnerable_flag FROM pnc_customers"))
        assert sqlstate(e.value) == "42501"


def test_customer_cannot_write_to_ledger_tables(rollback_session):
    for stmt in ("DELETE FROM pnc_transactions", "UPDATE pnc_accounts SET balance = 0", "DELETE FROM pnc_monthly_statements"):
        with rollback_session("customer", "C001", customer_id="C001") as c:
            with pytest.raises(DBAPIError) as e:
                c.execute(text(stmt))
            assert sqlstate(e.value) == "42501", stmt


def test_customer_cannot_write_other_customers_goal(rollback_session):
    with rollback_session("customer", "C001", customer_id="C001") as c:
        c.execute(text("SAVEPOINT s"))   # control: inserting for oneself is allowed
        c.execute(text("INSERT INTO pnc_savings_goals(customer_id, name, target_amount, deadline) VALUES ('C001','mine',100,'2027-01-01')"))
        c.execute(text("ROLLBACK TO SAVEPOINT s"))
        with pytest.raises(DBAPIError) as e:
            c.execute(text("INSERT INTO pnc_savings_goals(customer_id, name, target_amount, deadline) VALUES ('C002','x',100,'2027-01-01')"))
        assert sqlstate(e.value) == "42501"   # row-level security WITH CHECK violation

def test_customer_cannot_forge_audit_rows(rollback_session):
    with rollback_session("customer", "C001", customer_id="C001") as c:
        with pytest.raises(DBAPIError) as e:
            c.execute(text("INSERT INTO audit_log(actor_id, role, action, result) VALUES ('C001','customer','forged','allowed')"))
        assert sqlstate(e.value) == "42501"


def test_customer_cannot_read_audit_log(rollback_session):
    with rollback_session("customer", "C001", customer_id="C001") as c:
        with pytest.raises(DBAPIError) as e:
            c.execute(text("SELECT 1 FROM audit_log"))
        assert sqlstate(e.value) == "42501"


def test_non_customer_tables_are_closed_to_customers(rollback_session):
    """The database still holds legacy employee-side tables; customers must not reach any of them."""
    for table in ("prospects", "credit_decisions", "benefit_redemptions", "access_grants", "employees"):
        with rollback_session("customer", "C001", customer_id="C001") as c:
            with pytest.raises(DBAPIError) as e:
                c.execute(text(f"SELECT 1 FROM {table}"))
            assert sqlstate(e.value) == "42501", table


def test_audit_log_is_append_only_even_for_the_owner(rollback_session):
    with rollback_session() as c:
        with pytest.raises(DBAPIError):
            c.execute(text("UPDATE audit_log SET result = 'allowed'"))
    with rollback_session() as c:
        with pytest.raises(DBAPIError):
            c.execute(text("TRUNCATE audit_log"))
