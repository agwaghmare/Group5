-- Regular PostgreSQL tables initially; no unverified Timescale hypertable claims.
DO $$
DECLARE r text; t text;
BEGIN
  FOREACH r IN ARRAY ARRAY['finpilot_gateway','app_credit_analyst','app_service_specialist','app_marketing_analyst','app_portfolio_manager','app_compliance_analyst','app_auditor','app_benefits_admin']
  LOOP
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname=r) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN NOINHERIT', r);
    END IF;
    EXECUTE format('GRANT USAGE ON SCHEMA staff_app TO %I', r);
  END LOOP;
  GRANT app_credit_analyst, app_service_specialist, app_marketing_analyst,
    app_portfolio_manager, app_compliance_analyst, app_auditor, app_benefits_admin TO finpilot_gateway;
  FOREACH t IN ARRAY ARRAY['employees','prospects','credit_profiles','protected','links','policies','grants','runs','decisions','cases','case_events','catalog','benefit_rules','redemptions','audit','sessions','campaigns','anomalies','permissions']
  LOOP
    EXECUTE format('REVOKE ALL ON staff_app.%I FROM PUBLIC', t);
    EXECUTE format('ALTER TABLE staff_app.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE staff_app.%I FORCE ROW LEVEL SECURITY', t);
    -- Migration owner is administrative only, never the runtime credential.
    EXECUTE format('CREATE POLICY installer ON staff_app.%I TO %I USING (true) WITH CHECK (true)', t, current_user);
  END LOOP;
END $$;
REVOKE ALL ON SCHEMA staff_app FROM PUBLIC;
GRANT SELECT,INSERT ON staff_app.sessions TO finpilot_gateway;
GRANT SELECT ON staff_app.employees TO finpilot_gateway;
CREATE POLICY gateway_sessions ON staff_app.sessions TO finpilot_gateway USING (true) WITH CHECK (true);
CREATE POLICY gateway_employees ON staff_app.employees FOR SELECT TO finpilot_gateway USING (true);

CREATE FUNCTION staff_app.employee_id() RETURNS text LANGUAGE sql STABLE
SET search_path=pg_catalog AS $$ SELECT current_setting('app.employee_id', true) $$;
REVOKE ALL ON FUNCTION staff_app.employee_id() FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
  FOREACH r IN ARRAY ARRAY['app_credit_analyst','app_service_specialist','app_marketing_analyst','app_portfolio_manager','app_compliance_analyst','app_auditor','app_benefits_admin'] LOOP
    EXECUTE format('GRANT SELECT ON staff_app.employees, staff_app.catalog, staff_app.benefit_rules, staff_app.permissions, staff_app.redemptions TO %I',r);
    EXECUTE format('GRANT INSERT ON staff_app.redemptions TO %I',r);
    EXECUTE format('GRANT SELECT,DELETE ON staff_app.sessions TO %I',r);
    EXECUTE format('GRANT EXECUTE ON FUNCTION staff_app.employee_id() TO %I',r);
  END LOOP;
END $$;
CREATE POLICY employee_self ON staff_app.employees FOR SELECT USING (id=staff_app.employee_id());
CREATE POLICY own_sessions ON staff_app.sessions USING (payload->>'employee_id'=staff_app.employee_id());
CREATE POLICY catalog_read ON staff_app.catalog FOR SELECT USING (true);
CREATE POLICY rules_read ON staff_app.benefit_rules FOR SELECT USING (true);
CREATE POLICY permission_read ON staff_app.permissions FOR SELECT USING (true);
CREATE POLICY redemptions_read ON staff_app.redemptions FOR SELECT USING (owner=staff_app.employee_id());
CREATE POLICY redemptions_insert ON staff_app.redemptions FOR INSERT WITH CHECK (owner=staff_app.employee_id() AND payload->>'employee_id'=staff_app.employee_id());
CREATE POLICY admin_ledger ON staff_app.redemptions FOR SELECT TO app_benefits_admin USING (true);
GRANT INSERT ON staff_app.catalog,staff_app.benefit_rules TO app_benefits_admin;
CREATE POLICY admin_catalog ON staff_app.catalog FOR INSERT TO app_benefits_admin WITH CHECK (true);
CREATE POLICY admin_rules ON staff_app.benefit_rules FOR INSERT TO app_benefits_admin WITH CHECK (true);

GRANT SELECT ON staff_app.prospects,staff_app.credit_profiles,staff_app.links,staff_app.policies,staff_app.grants,staff_app.runs,staff_app.decisions TO app_credit_analyst;
GRANT INSERT ON staff_app.grants,staff_app.runs,staff_app.decisions TO app_credit_analyst;
CREATE POLICY own_links ON staff_app.links FOR SELECT TO app_credit_analyst USING (owner=staff_app.employee_id());
CREATE POLICY own_grants ON staff_app.grants FOR SELECT TO app_credit_analyst USING (owner=staff_app.employee_id());
CREATE POLICY prospect_queue ON staff_app.prospects FOR SELECT TO app_credit_analyst USING (
 owner=staff_app.employee_id() OR EXISTS(SELECT FROM staff_app.grants g WHERE g.owner=staff_app.employee_id() AND g.payload->>'prospect_id'=prospects.id AND (g.payload->>'expires_at')::timestamptz>now()));
CREATE POLICY profile_granted ON staff_app.credit_profiles FOR SELECT TO app_credit_analyst USING (
 EXISTS(SELECT FROM staff_app.grants g WHERE g.owner=staff_app.employee_id() AND g.payload->>'prospect_id'=credit_profiles.id AND (g.payload->>'expires_at')::timestamptz>now()));
CREATE POLICY policy_read ON staff_app.policies FOR SELECT TO app_credit_analyst,app_compliance_analyst,app_auditor USING (true);
GRANT SELECT ON staff_app.policies TO app_compliance_analyst,app_auditor;
CREATE POLICY analyst_runs ON staff_app.runs FOR SELECT TO app_credit_analyst USING (owner=staff_app.employee_id() AND EXISTS(
 SELECT FROM staff_app.grants g WHERE g.id=runs.payload->>'grant_id' AND (g.payload->>'expires_at')::timestamptz>now()));
CREATE POLICY insert_runs ON staff_app.runs FOR INSERT TO app_credit_analyst WITH CHECK (owner=staff_app.employee_id() AND payload->>'employee_id'=staff_app.employee_id() AND EXISTS(
 SELECT FROM staff_app.grants g WHERE g.id=runs.payload->>'grant_id' AND g.payload->>'prospect_id'=runs.payload->>'prospect_id' AND (g.payload->>'expires_at')::timestamptz>now()));
CREATE POLICY own_decisions ON staff_app.decisions TO app_credit_analyst USING (owner=staff_app.employee_id()) WITH CHECK (
 owner=staff_app.employee_id() AND payload->>'employee_id'=staff_app.employee_id() AND EXISTS (SELECT FROM staff_app.runs r WHERE r.id=decisions.payload->>'run_id'));
GRANT SELECT ON staff_app.decisions TO app_compliance_analyst;
CREATE POLICY compliance_decisions ON staff_app.decisions FOR SELECT TO app_compliance_analyst USING (true);

CREATE FUNCTION staff_app.grant_metadata(prospect_id text, reason text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,staff_app AS $$
 SELECT payload FROM staff_app.prospects WHERE id=prospect_id
 AND (owner=staff_app.employee_id() OR length(trim(reason))>=10)
$$;
CREATE FUNCTION staff_app.valid_grant(data jsonb) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,staff_app AS $$
 SELECT COALESCE(
 data->>'employee_id'=staff_app.employee_id()
 AND data->>'purpose' IN ('application_review','senior_review','quality_review')
 AND (data->>'expires_at')::timestamptz > now()
 AND (data->>'expires_at')::timestamptz <= now()+interval '60 minutes'
 AND EXISTS(SELECT FROM staff_app.prospects p WHERE p.id=data->>'prospect_id'
   AND p.payload->>'application_ref'=data->>'reference_id'
   AND (p.owner=staff_app.employee_id() OR length(trim(data->>'break_glass_reason'))>=10))
 AND NOT EXISTS(SELECT FROM staff_app.links l WHERE l.owner=staff_app.employee_id() AND l.payload->>'prospect_id'=data->>'prospect_id'),false)
$$;
REVOKE ALL ON FUNCTION staff_app.grant_metadata(text,text),staff_app.valid_grant(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION staff_app.grant_metadata(text,text),staff_app.valid_grant(jsonb) TO app_credit_analyst;
CREATE POLICY grant_insert ON staff_app.grants FOR INSERT TO app_credit_analyst WITH CHECK (owner=staff_app.employee_id() AND staff_app.valid_grant(payload));

GRANT SELECT,UPDATE ON staff_app.cases TO app_service_specialist;
GRANT SELECT,INSERT ON staff_app.case_events TO app_service_specialist;
CREATE POLICY assigned_cases ON staff_app.cases TO app_service_specialist USING (owner=staff_app.employee_id()) WITH CHECK (owner=staff_app.employee_id());
CREATE POLICY assigned_events ON staff_app.case_events TO app_service_specialist USING (owner=staff_app.employee_id()) WITH CHECK (owner=staff_app.employee_id());

CREATE VIEW staff_app.review_runs WITH (security_barrier=true) AS
 SELECT id,owner,payload-'input_snapshot'-'policy_snapshot'-'input_hash' AS payload FROM staff_app.runs;
REVOKE ALL ON staff_app.review_runs FROM PUBLIC;
GRANT SELECT ON staff_app.review_runs TO app_compliance_analyst;

CREATE FUNCTION staff_app.write_audit(data jsonb) RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,staff_app AS $$
BEGIN
 INSERT INTO staff_app.audit(id,owner,payload) VALUES(data->>'id','',
 data || jsonb_build_object('actor',COALESCE(staff_app.employee_id(),'anonymous')));
END $$;
REVOKE ALL ON FUNCTION staff_app.write_audit(jsonb) FROM PUBLIC;
GRANT SELECT ON staff_app.audit TO app_auditor,app_compliance_analyst;
CREATE POLICY audit_read ON staff_app.audit FOR SELECT TO app_auditor,app_compliance_analyst USING (true);
DO $$ DECLARE r text; BEGIN
 FOREACH r IN ARRAY ARRAY['finpilot_gateway','app_credit_analyst','app_service_specialist','app_marketing_analyst','app_portfolio_manager','app_compliance_analyst','app_auditor','app_benefits_admin'] LOOP
 EXECUTE format('GRANT EXECUTE ON FUNCTION staff_app.write_audit(jsonb) TO %I',r);
 END LOOP;
END $$;

CREATE FUNCTION staff_app.research_metrics() RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,staff_app AS $$
 WITH outcomes AS(SELECT payload->>'outcome' AS outcome,count(*) AS n FROM staff_app.runs GROUP BY 1),
 decisions AS(SELECT count(*) AS n,avg((payload->>'override')::boolean::int) AS rate FROM staff_app.decisions)
 SELECT jsonb_build_object('group_size',(SELECT count(*) FROM staff_app.runs),
 'outcomes',COALESCE((SELECT jsonb_object_agg(outcome,CASE WHEN n>=5 THEN n END) FROM outcomes),'{}'),
 'decision_count',CASE WHEN n>=5 THEN n END,'override_rate',CASE WHEN n>=5 THEN rate END,
 'suppression_threshold',5,'suppression_notice','Groups smaller than five are suppressed.') FROM decisions
$$;
CREATE FUNCTION staff_app.fairness_metrics() RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,staff_app AS $$
 WITH latest AS(SELECT DISTINCT ON (payload->>'prospect_id') payload FROM staff_app.runs ORDER BY payload->>'prospect_id',payload->>'run_at' DESC),
 groups AS(SELECT p.payload->>'group_label' AS label,count(*) AS n,avg((l.payload->>'outcome'='MEETS_POLICY')::int) AS rate
 FROM latest l JOIN staff_app.protected p ON p.id=l.payload->>'prospect_id' GROUP BY 1)
 SELECT COALESCE(jsonb_object_agg(label,jsonb_build_object('n',n,'meets_policy_rate',rate)),'{}') FROM groups
$$;
REVOKE ALL ON FUNCTION staff_app.research_metrics(),staff_app.fairness_metrics() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION staff_app.research_metrics() TO app_portfolio_manager;
GRANT EXECUTE ON FUNCTION staff_app.fairness_metrics() TO app_compliance_analyst;
GRANT SELECT,INSERT ON staff_app.campaigns TO app_marketing_analyst;
CREATE POLICY own_campaigns ON staff_app.campaigns TO app_marketing_analyst USING(owner=staff_app.employee_id()) WITH CHECK(owner=staff_app.employee_id());

CREATE FUNCTION staff_app.immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'append-only resource'; END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['audit','runs','decisions','case_events','redemptions','policies','benefit_rules','catalog'] LOOP
 EXECUTE format('CREATE TRIGGER append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON staff_app.%I FOR EACH STATEMENT EXECUTE FUNCTION staff_app.immutable()',t);
 END LOOP;
END $$;

