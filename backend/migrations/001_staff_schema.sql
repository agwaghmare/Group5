-- Additive employee schema. Never drops or alters existing pnc/meta datasets.
CREATE SCHEMA IF NOT EXISTS staff_app;
CREATE TABLE IF NOT EXISTS staff_app.schema_migrations(version text PRIMARY KEY);
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['employees','prospects','credit_profiles','protected','links','policies','grants','runs','decisions','cases','case_events','catalog','benefit_rules','redemptions','audit','sessions','campaigns','anomalies','permissions']
  LOOP
    EXECUTE format('CREATE TABLE IF NOT EXISTS staff_app.%I (id text PRIMARY KEY, owner text NOT NULL DEFAULT '''', payload jsonb NOT NULL)', t);
  END LOOP;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS redemption_idempotency ON staff_app.redemptions(owner, (payload->>'request_id'));
CREATE UNIQUE INDEX IF NOT EXISTS decision_run_unique ON staff_app.decisions((payload->>'run_id'));

