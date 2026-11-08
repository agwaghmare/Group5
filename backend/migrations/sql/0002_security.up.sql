-- FinPilot security layer: DB roles, RLS, masked views, purpose-gated functions, immutability.
SET search_path = finpilot, public;

-- ------------------------------------------------------------------ roles (NOLOGIN; assumed with SET LOCAL ROLE)
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['customer','credit_analyst','service_specialist','marketing_analyst',
                           'portfolio_manager','compliance_analyst','auditor','benefits_admin']
  LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_' || r) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN NOINHERIT NOBYPASSRLS', 'app_' || r);
    END IF;
    EXECUTE format('GRANT %I TO %I', 'app_' || r, current_user);
    EXECUTE format('GRANT USAGE ON SCHEMA finpilot TO %I', 'app_' || r);
  END LOOP;
END $$;

-- ------------------------------------------------------------------ session-context helpers
CREATE FUNCTION cur_actor()      RETURNS text LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('app.actor_id', true), '') $$;
CREATE FUNCTION cur_role()       RETURNS text LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('app.role', true), '') $$;
CREATE FUNCTION cur_org()        RETURNS text LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('app.org', true), '') $$;
CREATE FUNCTION cur_customer()   RETURNS text LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('app.customer_id', true), '') $$;
CREATE FUNCTION cur_employee()   RETURNS text LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('app.employee_id', true), '') $$;
CREATE FUNCTION cur_grant()      RETURNS text LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('app.grant_id', true), '') $$;
CREATE FUNCTION cur_request()    RETURNS text LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('app.request_id', true), '') $$;
CREATE FUNCTION cur_break_glass() RETURNS boolean LANGUAGE sql STABLE AS $$ SELECT coalesce(nullif(current_setting('app.break_glass', true), '')::boolean, false) $$;

-- Secrets used only inside owner-defined views (no role has any privilege on this table).
CREATE TABLE system_secrets (key text PRIMARY KEY, value text NOT NULL);
INSERT INTO system_secrets VALUES ('marketing_token_salt', gen_random_uuid()::text);

-- ------------------------------------------------------------------ audit (append-only)
CREATE FUNCTION _audit(p_actor text, p_role text, p_org text, p_action text, p_resource text, p_purpose text,
                       p_grant text, p_result text, p_break_glass boolean, p_request text, p_detail jsonb)
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = finpilot, public AS $$
  INSERT INTO audit_log(actor_id, role, org, action, resource, purpose, grant_id, result, break_glass, request_id, detail)
  VALUES (coalesce(p_actor,'unknown'), coalesce(p_role,'unknown'), 'pnc', p_action, p_resource, p_purpose,
          p_grant, p_result, coalesce(p_break_glass,false), p_request, coalesce(p_detail,'{}'::jsonb))
$$;

-- Callable by app roles; identity comes from the transaction-local context, never from parameters.
CREATE FUNCTION log_audit(p_action text, p_resource text, p_purpose text, p_result text, p_detail jsonb DEFAULT '{}')
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = finpilot, public AS $$
  SELECT _audit(cur_actor(), cur_role(), cur_org(), p_action, p_resource, p_purpose, cur_grant(),
                p_result, cur_break_glass(), cur_request(), p_detail)
$$;

-- Owner-only: lets the API record a denial in its own transaction after the request transaction aborted.
CREATE FUNCTION log_audit_as(p_actor text, p_role text, p_action text, p_resource text, p_purpose text,
                             p_grant text, p_result text, p_break_glass boolean, p_request text, p_detail jsonb DEFAULT '{}')
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = finpilot, public AS $$
  SELECT _audit(p_actor, p_role, 'pnc', p_action, p_resource, p_purpose, p_grant, p_result, p_break_glass, p_request, p_detail)
$$;

-- ------------------------------------------------------------------ immutability
CREATE FUNCTION forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% on finpilot.% is not permitted: table is append-only', TG_OP, TG_TABLE_NAME
    USING ERRCODE = 'integrity_constraint_violation';
END $$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['audit_log','credit_research_runs','credit_decisions','credit_policies',
                           'benefit_redemptions','benefit_catalog','benefit_rules','case_events']
  LOOP
    EXECUTE format('CREATE TRIGGER trg_%1$s_immutable BEFORE UPDATE OR DELETE ON finpilot.%1$I
                    FOR EACH ROW EXECUTE FUNCTION finpilot.forbid_mutation()', t);
    EXECUTE format('CREATE TRIGGER trg_%1$s_notruncate BEFORE TRUNCATE ON finpilot.%1$I
                    FOR EACH STATEMENT EXECUTE FUNCTION finpilot.forbid_mutation()', t);
  END LOOP;
END $$;

-- ------------------------------------------------------------------ RLS: enable everywhere sensitive
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['pnc_customers','pnc_accounts','pnc_transactions','pnc_monthly_statements',
    'pnc_balance_history','pnc_income_history','pnc_recurring_obligations','pnc_savings_goals',
    'pnc_health_snapshots','pnc_forecast_results','pnc_financial_scenarios','pnc_scenario_results',
    'pnc_debt_plans','pnc_fraud_events','pnc_fraud_cases','pnc_fraud_case_history','pnc_consents',
    'employees','employee_links','prospects','prospect_credit_profile','access_grants','credit_research_runs',
    'credit_decisions','cases','case_events','portfolio_snapshots','campaigns','benefit_redemptions','audit_log']
  LOOP
    EXECUTE format('ALTER TABLE finpilot.%I ENABLE ROW LEVEL SECURITY', t);
  END LOOP;
END $$;
ALTER TABLE compliance.prospect_protected ENABLE ROW LEVEL SECURITY;  -- no policy for any app role

-- ------------------------------------------------------------------ customer: own rows only
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['pnc_customers','pnc_accounts','pnc_transactions','pnc_monthly_statements',
    'pnc_balance_history','pnc_income_history','pnc_recurring_obligations','pnc_savings_goals',
    'pnc_health_snapshots','pnc_forecast_results','pnc_financial_scenarios','pnc_scenario_results',
    'pnc_debt_plans','pnc_fraud_events','pnc_fraud_cases','pnc_fraud_case_history','pnc_consents']
  LOOP
    EXECUTE format($f$CREATE POLICY customer_own ON finpilot.%I FOR ALL TO app_customer
                      USING (customer_id = finpilot.cur_customer())
                      WITH CHECK (customer_id = finpilot.cur_customer())$f$, t);
  END LOOP;
END $$;

GRANT SELECT ON pnc_accounts, pnc_transactions, pnc_monthly_statements, pnc_balance_history, pnc_income_history,
                pnc_recurring_obligations, pnc_health_snapshots, pnc_forecast_results, pnc_financial_scenarios,
                pnc_scenario_results, pnc_debt_plans, pnc_fraud_events, pnc_fraud_cases, pnc_fraud_case_history,
                pnc_consents, pnc_savings_goals TO app_customer;
GRANT SELECT (customer_id, display_name, age, city, pay_frequency, annual_income, income_sources_count,
              credit_score, preferred_channel, marketing_consent, dataset_version, source_type)
      ON pnc_customers TO app_customer;                      -- vulnerable_flag is never exposed to the customer API
GRANT INSERT, UPDATE, DELETE ON pnc_savings_goals TO app_customer;
GRANT INSERT ON pnc_financial_scenarios, pnc_scenario_results, pnc_forecast_results, pnc_debt_plans,
                pnc_health_snapshots, pnc_fraud_cases, pnc_fraud_case_history TO app_customer;
GRANT INSERT, UPDATE ON pnc_consents TO app_customer;
GRANT USAGE ON SEQUENCE pnc_fraud_case_history_history_id_seq TO app_customer;

-- customer may only open a 'new' unassigned case about themselves and read their own cases
CREATE POLICY customer_cases_select ON cases FOR SELECT TO app_customer USING (customer_id = cur_customer());
CREATE POLICY customer_cases_insert ON cases FOR INSERT TO app_customer
  WITH CHECK (customer_id = cur_customer() AND status = 'new' AND assigned_to IS NULL);
GRANT SELECT, INSERT ON cases TO app_customer;

-- ------------------------------------------------------------------ employees (all staff roles see only themselves)
CREATE POLICY employee_self ON employees FOR SELECT TO app_credit_analyst, app_service_specialist,
  app_marketing_analyst, app_portfolio_manager, app_compliance_analyst, app_auditor, app_benefits_admin
  USING (employee_id = cur_employee());
GRANT SELECT ON employees TO app_credit_analyst, app_service_specialist, app_marketing_analyst,
  app_portfolio_manager, app_compliance_analyst, app_auditor, app_benefits_admin;
GRANT SELECT ON role_permissions, credit_policies, benefit_catalog, benefit_rules TO
  app_credit_analyst, app_service_specialist, app_marketing_analyst, app_portfolio_manager,
  app_compliance_analyst, app_auditor, app_benefits_admin;

-- ------------------------------------------------------------------ credit analyst: purpose-gated, blind review
CREATE FUNCTION grant_ok(p_prospect text) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = finpilot, public AS $$
  SELECT EXISTS (SELECT 1 FROM access_grants g
                  WHERE g.grant_id::text = cur_grant() AND g.analyst_id = cur_employee()
                    AND g.prospect_id = p_prospect AND g.state = 'active' AND g.expires_at > clock_timestamp())
$$;
CREATE FUNCTION break_glass_ok(p_prospect text) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = finpilot, public AS $$
  SELECT EXISTS (SELECT 1 FROM access_grants g
                  WHERE g.analyst_id = cur_employee() AND g.prospect_id = p_prospect AND g.break_glass
                    AND g.state = 'active' AND g.expires_at > clock_timestamp())
$$;
REVOKE EXECUTE ON FUNCTION grant_ok(text), break_glass_ok(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION grant_ok(text), break_glass_ok(text) TO app_credit_analyst;

-- queue: only non-identifying columns of assigned prospects
GRANT SELECT (prospect_id, product, application_ref, assigned_to, status) ON prospects TO app_credit_analyst;
CREATE POLICY analyst_prospect_queue ON prospects FOR SELECT TO app_credit_analyst
  USING (assigned_to = cur_employee() OR break_glass_ok(prospect_id));

-- credit file: only with an active, prospect-bound grant
GRANT SELECT ON prospect_credit_profile TO app_credit_analyst;
CREATE POLICY analyst_credit_file ON prospect_credit_profile FOR SELECT TO app_credit_analyst
  USING (grant_ok(prospect_id));

GRANT SELECT ON access_grants TO app_credit_analyst;       -- grants are created only via create_access_grant()
CREATE POLICY analyst_own_grants ON access_grants FOR SELECT TO app_credit_analyst USING (analyst_id = cur_employee());

GRANT SELECT, INSERT ON credit_research_runs TO app_credit_analyst;
CREATE POLICY analyst_runs_select ON credit_research_runs FOR SELECT TO app_credit_analyst USING (analyst_id = cur_employee());
CREATE POLICY analyst_runs_insert ON credit_research_runs FOR INSERT TO app_credit_analyst
  WITH CHECK (analyst_id = cur_employee() AND grant_ok(prospect_id));

GRANT SELECT, INSERT ON credit_decisions TO app_credit_analyst;
CREATE POLICY analyst_dec_select ON credit_decisions FOR SELECT TO app_credit_analyst USING (analyst_id = cur_employee());
CREATE POLICY analyst_dec_insert ON credit_decisions FOR INSERT TO app_credit_analyst
  WITH CHECK (analyst_id = cur_employee() AND grant_ok(prospect_id));

CREATE FUNCTION create_access_grant(p_prospect_id text, p_purpose text, p_application_ref text,
    p_ttl_minutes integer DEFAULT 60, p_break_glass boolean DEFAULT false,
    p_break_glass_reason text DEFAULT NULL, p_authorized_by text DEFAULT NULL)
RETURNS TABLE (ok boolean, grant_id uuid, reason text, expires_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = finpilot, public AS $$
DECLARE
  v_emp text := cur_employee();
  v_role text;
  v_pros prospects%ROWTYPE;
  v_conflict boolean;
  v_auth_ok boolean := false;
  v_gid uuid;
  v_exp timestamptz;
  v_ttl integer := greatest(1, least(coalesce(p_ttl_minutes, 60), 240));
  v_reason text := NULL;
BEGIN
  SELECT e.role INTO v_role FROM employees e WHERE e.employee_id = v_emp AND e.status = 'active';
  IF v_role IS DISTINCT FROM 'credit_analyst' OR cur_role() IS DISTINCT FROM 'credit_analyst' THEN
    v_reason := 'role_not_permitted';
  ELSE
    SELECT * INTO v_pros FROM prospects p WHERE p.prospect_id = p_prospect_id;
    IF NOT FOUND THEN v_reason := 'unknown_prospect';
    ELSIF length(trim(coalesce(p_purpose, ''))) < 5 THEN v_reason := 'purpose_required';
    ELSIF p_application_ref IS DISTINCT FROM v_pros.application_ref THEN v_reason := 'application_reference_mismatch';
    ELSE
      SELECT EXISTS (SELECT 1 FROM employee_links l WHERE l.employee_id = v_emp
                      AND l.linked_kind = 'prospect' AND l.linked_id = p_prospect_id) INTO v_conflict;
      IF v_conflict THEN
        SELECT EXISTS (SELECT 1 FROM employees a WHERE a.employee_id = p_authorized_by
                        AND a.role = 'compliance_analyst' AND a.status = 'active') INTO v_auth_ok;
        IF NOT (p_break_glass AND v_auth_ok) THEN v_reason := 'conflict_of_interest'; END IF;
      END IF;
      IF v_reason IS NULL AND v_pros.assigned_to IS DISTINCT FROM v_emp AND NOT p_break_glass THEN
        v_reason := 'not_assigned';
      END IF;
      IF v_reason IS NULL AND p_break_glass AND length(trim(coalesce(p_break_glass_reason, ''))) < 20 THEN
        v_reason := 'break_glass_reason_required';
      END IF;
    END IF;
  END IF;

  IF v_reason IS NOT NULL THEN
    PERFORM _audit(cur_actor(), cur_role(), 'pnc', 'credit_file.grant', p_prospect_id, p_purpose, NULL,
                   'denied', p_break_glass, cur_request(), jsonb_build_object('reason', v_reason));
    RETURN QUERY SELECT false, NULL::uuid, v_reason, NULL::timestamptz;
    RETURN;
  END IF;

  v_exp := clock_timestamp() + make_interval(mins => v_ttl);
  INSERT INTO access_grants(analyst_id, prospect_id, purpose, application_ref, break_glass,
                            break_glass_reason, authorized_by, expires_at)
  VALUES (v_emp, p_prospect_id, trim(p_purpose), p_application_ref, p_break_glass,
          p_break_glass_reason, CASE WHEN v_conflict THEN p_authorized_by END, v_exp)
  RETURNING access_grants.grant_id INTO v_gid;
  PERFORM _audit(cur_actor(), cur_role(), 'pnc', 'credit_file.grant', p_prospect_id, p_purpose, v_gid::text,
                 'allowed', p_break_glass, cur_request(),
                 jsonb_build_object('expires_at', v_exp, 'break_glass', p_break_glass, 'conflict_override', v_conflict));
  RETURN QUERY SELECT true, v_gid, NULL::text, v_exp;
END $$;
REVOKE EXECUTE ON FUNCTION create_access_grant(text,text,text,integer,boolean,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION create_access_grant(text,text,text,integer,boolean,text,text) TO app_credit_analyst;

-- ------------------------------------------------------------------ service specialist: assigned cases only
CREATE POLICY specialist_cases ON cases FOR ALL TO app_service_specialist
  USING (assigned_to = cur_employee()) WITH CHECK (assigned_to = cur_employee());
GRANT SELECT ON cases TO app_service_specialist;
GRANT UPDATE (status) ON cases TO app_service_specialist;

CREATE POLICY specialist_events_select ON case_events FOR SELECT TO app_service_specialist
  USING (EXISTS (SELECT 1 FROM cases c WHERE c.case_id = case_events.case_id AND c.assigned_to = cur_employee()));
CREATE POLICY specialist_events_insert ON case_events FOR INSERT TO app_service_specialist
  WITH CHECK (actor_id = cur_employee() AND event_type = 'note'
              AND EXISTS (SELECT 1 FROM cases c WHERE c.case_id = case_events.case_id AND c.assigned_to = cur_employee()));
GRANT SELECT, INSERT ON case_events TO app_service_specialist;

-- unassigned queue: no customer identity, no context
CREATE VIEW v_case_queue WITH (security_barrier = true) AS
  SELECT case_id, source, sla_due, created_at FROM cases WHERE status = 'new' AND assigned_to IS NULL;
GRANT SELECT ON v_case_queue TO app_service_specialist;

CREATE FUNCTION claim_case(p_case_id uuid) RETURNS TABLE (ok boolean, reason text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = finpilot, public AS $$
DECLARE v_emp text := cur_employee(); v_role text; v_n integer;
BEGIN
  SELECT e.role INTO v_role FROM employees e WHERE e.employee_id = v_emp AND e.status = 'active';
  IF v_role IS DISTINCT FROM 'service_specialist' OR cur_role() IS DISTINCT FROM 'service_specialist' THEN
    PERFORM _audit(cur_actor(), cur_role(), 'pnc', 'case.claim', p_case_id::text, NULL, NULL, 'denied', false, cur_request(),
                   '{"reason":"role_not_permitted"}');
    RETURN QUERY SELECT false, 'role_not_permitted'; RETURN;
  END IF;
  UPDATE cases SET assigned_to = v_emp, status = 'assigned'
   WHERE case_id = p_case_id AND status = 'new' AND assigned_to IS NULL;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  IF v_n = 0 THEN
    PERFORM _audit(cur_actor(), cur_role(), 'pnc', 'case.claim', p_case_id::text, NULL, NULL, 'denied', false, cur_request(),
                   '{"reason":"not_claimable"}');
    RETURN QUERY SELECT false, 'not_claimable'; RETURN;
  END IF;
  INSERT INTO case_events(case_id, actor_id, event_type, from_status, to_status, note)
  VALUES (p_case_id, v_emp, 'assignment', 'new', 'assigned', 'claimed by specialist');
  PERFORM _audit(cur_actor(), cur_role(), 'pnc', 'case.claim', p_case_id::text, NULL, NULL, 'allowed', false, cur_request(), '{}');
  RETURN QUERY SELECT true, NULL::text;
END $$;
REVOKE EXECUTE ON FUNCTION claim_case(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION claim_case(uuid) TO app_service_specialist;

-- status transitions: new->assigned (claim) -> in_progress -> resolved; automatic case_events row
CREATE FUNCTION trg_case_status() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = finpilot, public AS $$
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    IF NOT ((OLD.status = 'new' AND NEW.status = 'assigned') OR
            (OLD.status = 'assigned' AND NEW.status IN ('in_progress','resolved')) OR
            (OLD.status = 'in_progress' AND NEW.status = 'resolved')) THEN
      RAISE EXCEPTION 'invalid case status transition % -> %', OLD.status, NEW.status
        USING ERRCODE = 'check_violation';
    END IF;
    IF NOT (OLD.status = 'new' AND NEW.status = 'assigned') THEN
      INSERT INTO case_events(case_id, actor_id, event_type, from_status, to_status, note)
      VALUES (NEW.case_id, coalesce(cur_actor(), 'system'), 'status_change', OLD.status, NEW.status, NULL);
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_cases_status BEFORE UPDATE ON cases FOR EACH ROW EXECUTE FUNCTION trg_case_status();

-- ------------------------------------------------------------------ marketing: tokenized, consented, banded audience
CREATE VIEW v_marketing_audience WITH (security_barrier = true) AS
  SELECT substr(encode(sha256(convert_to(c.customer_id || (SELECT value FROM system_secrets
                                         WHERE key = 'marketing_token_salt'), 'UTF8')), 'hex'), 1, 16) AS audience_token,
         CASE WHEN c.annual_income < 30000 THEN '<30k' WHEN c.annual_income < 60000 THEN '30-60k'
              WHEN c.annual_income < 100000 THEN '60-100k' WHEN c.annual_income < 150000 THEN '100-150k'
              ELSE '150k+' END AS income_band,
         CASE WHEN c.age < 25 THEN '18-24' WHEN c.age < 35 THEN '25-34' WHEN c.age < 50 THEN '35-49'
              WHEN c.age < 65 THEN '50-64' ELSE '65+' END AS age_band,
         c.preferred_channel,
         CASE WHEN c.credit_score IS NULL THEN 'unknown' WHEN c.credit_score >= 740 THEN 'excellent'
              WHEN c.credit_score >= 670 THEN 'good' ELSE 'building' END AS credit_band,
         EXISTS (SELECT 1 FROM pnc_accounts a WHERE a.customer_id = c.customer_id AND a.account_type = 'savings') AS has_savings,
         EXISTS (SELECT 1 FROM pnc_accounts a WHERE a.customer_id = c.customer_id AND a.account_type = 'credit_card') AS has_credit_card
    FROM pnc_customers c
   WHERE c.marketing_consent AND NOT c.vulnerable_flag AND c.preferred_channel IS DISTINCT FROM 'none'
     AND NOT EXISTS (SELECT 1 FROM pnc_consents k WHERE k.customer_id = c.customer_id
                      AND k.scope = 'marketing' AND NOT k.granted);
GRANT SELECT ON v_marketing_audience TO app_marketing_analyst;
GRANT SELECT, INSERT ON campaigns TO app_marketing_analyst;
CREATE POLICY marketing_campaigns ON campaigns FOR ALL TO app_marketing_analyst
  USING (created_by = cur_employee()) WITH CHECK (created_by = cur_employee());

-- ------------------------------------------------------------------ portfolio: aggregates only, suppression pre-applied
GRANT SELECT ON portfolio_snapshots TO app_portfolio_manager, app_compliance_analyst;
CREATE POLICY portfolio_read ON portfolio_snapshots FOR SELECT TO app_portfolio_manager, app_compliance_analyst USING (true);

CREATE VIEW v_research_funnel WITH (security_barrier = true) AS
  SELECT policy_version, outcome, CASE WHEN count(*) < 5 THEN NULL ELSE count(*) END AS runs,
         count(*) < 5 AS suppressed
    FROM credit_research_runs GROUP BY policy_version, outcome;
CREATE VIEW v_override_rates WITH (security_barrier = true) AS
  SELECT policy_version, CASE WHEN count(*) < 5 THEN NULL ELSE count(*) END AS decisions,
         CASE WHEN count(*) < 5 THEN NULL ELSE count(*) FILTER (WHERE is_override) END AS overrides,
         count(*) < 5 AS suppressed
    FROM credit_decisions GROUP BY policy_version;
CREATE VIEW v_case_stats WITH (security_barrier = true) AS
  SELECT source, status, CASE WHEN count(*) < 5 THEN NULL ELSE count(*) END AS cases, count(*) < 5 AS suppressed
    FROM cases GROUP BY source, status;
GRANT SELECT ON v_research_funnel, v_override_rates, v_case_stats TO app_portfolio_manager, app_compliance_analyst;

-- ------------------------------------------------------------------ compliance: masked views and fairness function
CREATE VIEW v_prospect_token WITH (security_barrier = true) AS
  SELECT prospect_id,
         substr(encode(sha256(convert_to(prospect_id || (SELECT value FROM system_secrets
                 WHERE key = 'marketing_token_salt'), 'UTF8')), 'hex'), 1, 12) AS prospect_token
    FROM prospects;
CREATE VIEW v_runs_masked WITH (security_barrier = true) AS
  SELECT r.run_id, r.run_at, t.prospect_token, r.analyst_id, r.policy_version, r.outcome, r.pricing_tier,
         r.rule_results, r.missing_inputs, r.input_hash
    FROM credit_research_runs r JOIN v_prospect_token t USING (prospect_id);
CREATE VIEW v_override_queue WITH (security_barrier = true) AS
  SELECT d.decision_id, d.run_id, t.prospect_token, d.analyst_id, d.decision, d.engine_outcome,
         d.override_reason, d.rationale, d.reason_codes, d.policy_version, d.decided_at
    FROM credit_decisions d JOIN v_prospect_token t USING (prospect_id) WHERE d.is_override;
CREATE VIEW v_anomaly_queue WITH (security_barrier = true) AS
  SELECT e.event_id,
         substr(encode(sha256(convert_to(e.customer_id || (SELECT value FROM system_secrets
                 WHERE key = 'marketing_token_salt'), 'UTF8')), 'hex'), 1, 12) AS customer_token,
         e.posted_date, e.detector, e.anomaly_score, e.review_flag, e.model_version, e.supporting_factors,
         e.review_status, e.reviewed_by, e.reviewed_at, e.source_type
    FROM pnc_fraud_events e;
GRANT SELECT ON v_runs_masked, v_override_queue, v_anomaly_queue TO app_compliance_analyst;

CREATE FUNCTION review_anomaly(p_event_id uuid, p_status text, p_note text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = finpilot, public AS $$
DECLARE v_n integer;
BEGIN
  IF cur_role() IS DISTINCT FROM 'compliance_analyst' OR NOT EXISTS (
       SELECT 1 FROM employees e WHERE e.employee_id = cur_employee() AND e.role = 'compliance_analyst' AND e.status='active') THEN
    PERFORM _audit(cur_actor(), cur_role(), 'pnc', 'anomaly.review', p_event_id::text, NULL, NULL, 'denied', false, cur_request(), '{}');
    RETURN false;
  END IF;
  IF p_status NOT IN ('in_review','dismissed','escalated','confirmed_by_human_review') THEN
    RAISE EXCEPTION 'invalid review status %', p_status USING ERRCODE = 'check_violation';
  END IF;
  UPDATE pnc_fraud_events SET review_status = p_status, reviewed_by = cur_employee(), reviewed_at = now(),
         review_note = p_note WHERE event_id = p_event_id;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  PERFORM _audit(cur_actor(), cur_role(), 'pnc', 'anomaly.review', p_event_id::text, NULL, NULL,
                 CASE WHEN v_n = 1 THEN 'allowed' ELSE 'error' END, false, cur_request(), jsonb_build_object('status', p_status));
  RETURN v_n = 1;
END $$;
REVOKE EXECUTE ON FUNCTION review_anomaly(uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION review_anomaly(uuid,text,text) TO app_compliance_analyst;

-- Fairness monitor: latest run per prospect for a policy version; groups < 5 suppressed (illustrative 0.80 flag).
CREATE FUNCTION compliance.fairness_report(p_policy_version integer, p_min_group integer DEFAULT 5)
RETURNS TABLE (group_label text, n integer, meets integer, refer integer, does_not_meet integer,
               insufficient integer, meets_rate numeric, ratio_vs_highest numeric, flag text, suppressed boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = finpilot, compliance, public AS $$
BEGIN
  IF cur_role() NOT IN ('compliance_analyst') THEN
    RAISE EXCEPTION 'fairness_report requires compliance_analyst' USING ERRCODE = 'insufficient_privilege';
  END IF;
  PERFORM _audit(cur_actor(), cur_role(), 'pnc', 'fairness.report', 'policy_v' || p_policy_version, NULL, NULL,
                 'allowed', false, cur_request(), '{}');
  RETURN QUERY
  WITH latest AS (
    SELECT DISTINCT ON (r.prospect_id) r.prospect_id, r.outcome FROM credit_research_runs r
     WHERE r.policy_version = p_policy_version ORDER BY r.prospect_id, r.run_at DESC),
  agg AS (
    SELECT p.group_label AS g, count(*)::integer AS n,
           count(*) FILTER (WHERE l.outcome = 'MEETS_POLICY')::integer AS meets,
           count(*) FILTER (WHERE l.outcome = 'REFER')::integer AS refer,
           count(*) FILTER (WHERE l.outcome = 'DOES_NOT_MEET')::integer AS dnm,
           count(*) FILTER (WHERE l.outcome = 'INSUFFICIENT_DATA')::integer AS insuf
      FROM latest l JOIN prospect_protected p USING (prospect_id) GROUP BY p.group_label),
  rated AS (SELECT a.*, a.meets::numeric / nullif(a.n, 0) AS rate FROM agg a),
  best AS (SELECT max(rate) AS top FROM rated WHERE n >= p_min_group)
  SELECT r.g, r.n,
         CASE WHEN r.n < p_min_group THEN NULL ELSE r.meets END, CASE WHEN r.n < p_min_group THEN NULL ELSE r.refer END,
         CASE WHEN r.n < p_min_group THEN NULL ELSE r.dnm END, CASE WHEN r.n < p_min_group THEN NULL ELSE r.insuf END,
         CASE WHEN r.n < p_min_group THEN NULL ELSE round(r.rate, 4) END,
         CASE WHEN r.n < p_min_group OR b.top IS NULL OR b.top = 0 THEN NULL ELSE round(r.rate / b.top, 4) END,
         CASE WHEN r.n < p_min_group THEN 'suppressed_small_group'
              WHEN b.top IS NULL OR b.top = 0 THEN 'not_computable'
              WHEN r.rate / b.top < 0.80 THEN 'review_ratio_below_0.80_illustrative'
              ELSE 'ok' END,
         r.n < p_min_group
    FROM rated r CROSS JOIN best b ORDER BY r.g;
END $$;
REVOKE ALL ON FUNCTION compliance.fairness_report(integer, integer) FROM PUBLIC;
GRANT USAGE ON SCHEMA compliance TO app_compliance_analyst;
GRANT EXECUTE ON FUNCTION compliance.fairness_report(integer, integer) TO app_compliance_analyst;

-- ------------------------------------------------------------------ audit access
CREATE POLICY audit_read ON audit_log FOR SELECT TO app_auditor, app_compliance_analyst USING (org = 'pnc');
GRANT SELECT ON audit_log TO app_auditor, app_compliance_analyst;

-- ------------------------------------------------------------------ benefits
CREATE POLICY benefits_own ON benefit_redemptions FOR SELECT TO app_credit_analyst, app_service_specialist,
  app_marketing_analyst, app_portfolio_manager, app_compliance_analyst, app_auditor
  USING (employee_id = cur_employee());
CREATE POLICY benefits_admin_read ON benefit_redemptions FOR SELECT TO app_benefits_admin USING (true);
CREATE POLICY benefits_insert_own ON benefit_redemptions FOR INSERT TO app_credit_analyst, app_service_specialist,
  app_marketing_analyst, app_portfolio_manager, app_compliance_analyst, app_auditor, app_benefits_admin
  WITH CHECK (employee_id = cur_employee());
GRANT SELECT, INSERT ON benefit_redemptions TO app_credit_analyst, app_service_specialist, app_marketing_analyst,
  app_portfolio_manager, app_compliance_analyst, app_auditor, app_benefits_admin;
GRANT INSERT ON benefit_catalog, benefit_rules TO app_benefits_admin;

-- ------------------------------------------------------------------ function privilege hygiene
REVOKE EXECUTE ON FUNCTION _audit(text,text,text,text,text,text,text,text,boolean,text,jsonb) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION log_audit(text,text,text,text,jsonb) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION log_audit_as(text,text,text,text,text,text,text,boolean,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION log_audit(text,text,text,text,jsonb) TO app_customer, app_credit_analyst,
  app_service_specialist, app_marketing_analyst, app_portfolio_manager, app_compliance_analyst, app_auditor, app_benefits_admin;
GRANT EXECUTE ON FUNCTION cur_actor(), cur_role(), cur_org(), cur_customer(), cur_employee(), cur_grant(),
  cur_request(), cur_break_glass() TO app_customer, app_credit_analyst, app_service_specialist,
  app_marketing_analyst, app_portfolio_manager, app_compliance_analyst, app_auditor, app_benefits_admin;
