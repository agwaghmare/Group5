-- Reverses 0002_security: removes policies, views, functions, triggers, RLS flags and app_* roles.
SET search_path = finpilot, public;

DO $$
DECLARE p record; t text;
BEGIN
  FOR p IN SELECT schemaname, tablename, policyname FROM pg_policies WHERE schemaname IN ('finpilot','compliance') LOOP
    EXECUTE format('DROP POLICY %I ON %I.%I', p.policyname, p.schemaname, p.tablename);
  END LOOP;
  FOR t IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'finpilot' AND c.relkind IN ('r','p') AND c.relrowsecurity LOOP
    EXECUTE format('ALTER TABLE finpilot.%I DISABLE ROW LEVEL SECURITY', t);
  END LOOP;
  ALTER TABLE compliance.prospect_protected DISABLE ROW LEVEL SECURITY;
  FOREACH t IN ARRAY ARRAY['audit_log','credit_research_runs','credit_decisions','credit_policies',
                           'benefit_redemptions','benefit_catalog','benefit_rules','case_events']
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS trg_%1$s_immutable ON finpilot.%1$I', t);
    EXECUTE format('DROP TRIGGER IF EXISTS trg_%1$s_notruncate ON finpilot.%1$I', t);
  END LOOP;
END $$;

DROP TRIGGER IF EXISTS trg_cases_status ON cases;
DROP VIEW IF EXISTS v_case_queue, v_marketing_audience, v_research_funnel, v_override_rates, v_case_stats,
                    v_runs_masked, v_override_queue, v_anomaly_queue, v_prospect_token;
DROP FUNCTION IF EXISTS compliance.fairness_report(integer, integer);
DROP FUNCTION IF EXISTS review_anomaly(uuid, text, text), claim_case(uuid),
  create_access_grant(text,text,text,integer,boolean,text,text), grant_ok(text), break_glass_ok(text),
  trg_case_status(), forbid_mutation() CASCADE;
DROP FUNCTION IF EXISTS log_audit(text,text,text,text,jsonb), log_audit_as(text,text,text,text,text,text,text,boolean,text,jsonb),
  _audit(text,text,text,text,text,text,text,text,boolean,text,jsonb), cur_actor(), cur_role(), cur_org(),
  cur_customer(), cur_employee(), cur_grant(), cur_request(), cur_break_glass();
DROP TABLE IF EXISTS system_secrets;

DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['customer','credit_analyst','service_specialist','marketing_analyst',
                           'portfolio_manager','compliance_analyst','auditor','benefits_admin']
  LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_' || r) THEN
      EXECUTE format('DROP OWNED BY %I', 'app_' || r);
      EXECUTE format('DROP ROLE %I', 'app_' || r);
    END IF;
  END LOOP;
END $$;
