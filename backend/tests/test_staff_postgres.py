"""Opt-in direct SQL checks against a migrated dedicated PostgreSQL test DB.

STAFF_TEST_DATABASE_URL must use the non-owner API runtime login. These tests
rollback every transaction; they do not run migrations or reload cloud data.
"""
import json
import os
import unittest
from datetime import datetime, timedelta, timezone

from app.staff.seed import employees
from app.staff.store import ident


@unittest.skipUnless(os.environ.get('RUN_LEGACY_TIGER_TESTS') == '1' and os.environ.get('STAFF_TEST_DATABASE_URL'), 'Archived Tiger tests; inactive in SQLAlchemy local mode')
class PostgreSQLIsolation(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.psycopg = psycopg
        self.conn = psycopg.connect(os.environ['STAFF_TEST_DATABASE_URL'])
        privileged = self.conn.execute('SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()[0]
        self.assertFalse(privileged, 'Isolation tests must use a non-superuser runtime login')
        owner = self.conn.execute("SELECT EXISTS(SELECT FROM pg_tables WHERE schemaname='staff_app' AND tableowner=current_user)").fetchone()[0]
        self.assertFalse(owner, 'Isolation tests must not run as the migration owner')

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def assume(self, employee):
        self.conn.execute(f'SET LOCAL ROLE app_{employee["role"]}')
        self.conn.execute("SELECT set_config('app.employee_id',%s,true)",(employee['id'],))

    def test_every_role_every_base_table_and_masked_view(self):
        from app.staff.store import TABLES
        shared={'employees','catalog','benefit_rules','permissions','redemptions','sessions'}
        allowed={
            'credit_analyst':shared|{'prospects','credit_profiles','links','policies','grants','runs','decisions'},
            'service_specialist':shared|{'cases','case_events'},
            'marketing_analyst':shared|{'campaigns'},
            'portfolio_manager':shared,
            'compliance_analyst':shared|{'policies','decisions','audit'},
            'auditor':shared|{'policies','audit'},
            'benefits_admin':shared,
        }
        for employee in employees():
            self.assume(employee)
            for table in TABLES:
                if table in allowed[employee['role']]:
                    rows=self.conn.execute(f'SELECT id,owner,payload FROM staff_app."{table}"').fetchall()
                    if table in ('employees','sessions'):
                        self.assertTrue(all((r[0] if table=='employees' else r[2]['employee_id'])==employee['id'] for r in rows))
                    if table=='redemptions' and employee['role']!='benefits_admin':
                        self.assertTrue(all(r[1]==employee['id'] for r in rows))
                    if table=='prospects':
                        self.assertTrue(all('annual_income' not in r[2] and 'age' not in r[2] for r in rows))
                else:
                    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege, msg=(employee['role'],table)):
                        with self.conn.transaction():
                            self.conn.execute(f'SELECT payload FROM staff_app."{table}"').fetchall()
            if employee['role']=='compliance_analyst':
                for row in self.conn.execute('SELECT payload FROM staff_app.review_runs').fetchall():
                    self.assertNotIn('input_snapshot',row[0])
            self.conn.execute('RESET ROLE')

    def test_database_purpose_gate_expiry_and_conflict(self):
        self.assume(employees()[0])
        self.assertEqual(self.conn.execute("SELECT payload FROM staff_app.credit_profiles WHERE id='P001'").fetchall(),[])
        grant={'id':ident('G'), 'employee_id':'E001','prospect_id':'P001','purpose':'application_review',
               'reference_id':'APP-001','break_glass_reason':None,
               'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()}
        self.conn.execute('INSERT INTO staff_app.grants VALUES(%s,%s,%s)',(grant['id'],'E001',json.dumps(grant)))
        self.assertEqual(len(self.conn.execute("SELECT payload FROM staff_app.credit_profiles WHERE id='P001'").fetchall()),1)
        for changed in ({'prospect_id':'P005','reference_id':'APP-005'},
                        {'expires_at':'2020-01-01T00:00:00+00:00'},
                        {'employee_id':'E002'}, {'prospect_id':'P002','reference_id':'APP-002'}):
            bad={**grant,**changed,'id':ident('G')}
            with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                with self.conn.transaction():
                    self.conn.execute('INSERT INTO staff_app.grants VALUES(%s,%s,%s)',(bad['id'],'E001',json.dumps(bad)))

    def test_audit_and_research_cannot_be_mutated(self):
        for employee in employees():
            self.assume(employee)
            for table in ('audit','runs','decisions','redemptions','catalog','benefit_rules'):
                for operation in ('UPDATE '+f'staff_app.{table} SET owner=owner',
                                  'DELETE FROM '+f'staff_app.{table}', 'TRUNCATE '+f'staff_app.{table}'):
                    with self.assertRaises(self.psycopg.Error):
                        with self.conn.transaction():
                            self.conn.execute(operation)
            self.conn.execute('RESET ROLE')


if __name__=='__main__':
    unittest.main()
