-- 0005: app_users + role_catalog (Skill.md §3.1 / §3.5). Demo login identities; role never comes from the client.

SET search_path = finpilot, public;

CREATE TABLE role_catalog (
    role            text PRIMARY KEY,
    label           text NOT NULL,
    tabs            text[] NOT NULL,          -- ordered wheel tabs for this role
    home_route      text NOT NULL,            -- default route after login
    features        text[] NOT NULL,          -- feature-id prefixes / ids from the registry
    is_staff        boolean NOT NULL DEFAULT false
);

INSERT INTO role_catalog(role, label, tabs, home_route, features, is_staff) VALUES
 ('customer',            'Customer',                      ARRAY['home','finance','learn'],               '/finance',    ARRAY['fin.*','learn.*'], false),
 ('credit_analyst',      'Credit Analyst',                ARRAY['home','research','benefits','learn'],   '/research',   ARRAY['staff.access','staff.prospect','staff.creditresearch','staff.decision','staff.benefits','learn.explain'], true),
 ('service_specialist',  'Customer Service Specialist',   ARRAY['home','cases','benefits','learn'],      '/cases',      ARRAY['staff.access','staff.cases','staff.benefits','learn.explain'], true),
 ('marketing_analyst',   'Retention / Marketing Analyst', ARRAY['home','portfolio','benefits','learn'],  '/portfolio',  ARRAY['staff.access','staff.campaigns','staff.portfolio','staff.benefits','learn.explain'], true),
 ('portfolio_manager',   'Portfolio / Risk Manager',      ARRAY['home','portfolio','benefits','learn'],  '/portfolio',  ARRAY['staff.access','staff.portfolio','staff.benefits','learn.explain'], true),
 ('compliance_analyst',  'Compliance Analyst',            ARRAY['home','compliance','benefits','learn'], '/compliance', ARRAY['staff.access','staff.fairness','staff.anomaly','staff.audit','staff.decision','staff.benefits','learn.explain'], true),
 ('auditor',             'Auditor',                       ARRAY['home','compliance','benefits','learn'], '/compliance', ARRAY['staff.access','staff.audit','staff.benefits','learn.explain'], true),
 ('benefits_admin',      'Benefits Admin',                ARRAY['home','benefits','learn'],              '/benefits',   ARRAY['staff.access','staff.benefits','learn.explain'], true);

CREATE TABLE app_users (
    user_id         text PRIMARY KEY,
    login_name      text NOT NULL UNIQUE,
    password_hash   text NOT NULL,
    role            text NOT NULL REFERENCES role_catalog(role),
    org             text NOT NULL DEFAULT 'pnc' CHECK (org = 'pnc'),
    display_name    text NOT NULL,
    customer_id     text REFERENCES pnc_customers(customer_id),
    employee_id     text REFERENCES employees(employee_id),
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
    source_type     text NOT NULL DEFAULT 'synthetic_demo',
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT app_users_identity_chk CHECK (
        (role = 'customer' AND customer_id IS NOT NULL AND employee_id IS NULL)
        OR
        (role <> 'customer' AND employee_id IS NOT NULL AND customer_id IS NULL)
    )
);

CREATE INDEX app_users_role_idx ON app_users(role);
CREATE INDEX app_users_customer_idx ON app_users(customer_id) WHERE customer_id IS NOT NULL;
CREATE INDEX app_users_employee_idx ON app_users(employee_id) WHERE employee_id IS NOT NULL;

COMMENT ON TABLE app_users IS 'Demo login identities. Role and org are server-authoritative; never accept them from a request body.';
COMMENT ON TABLE role_catalog IS 'Skill.md §3.5 role → visible wheel tabs and default home route.';

-- Least-privilege: customers may read their own user row (for /me); staff rows stay owner-only for now.
ALTER TABLE app_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE role_catalog ENABLE ROW LEVEL SECURITY;

CREATE POLICY app_users_self_select ON app_users FOR SELECT TO app_customer
  USING (role = 'customer' AND customer_id = cur_customer() AND status = 'active');

CREATE POLICY role_catalog_read ON role_catalog FOR SELECT TO app_customer USING (true);

GRANT SELECT ON role_catalog TO app_customer;
GRANT SELECT ON app_users TO app_customer;

-- Staff DB roles can read the catalog (UI shell); user rows for staff are resolved by the API as owner then SET LOCAL ROLE.
GRANT SELECT ON role_catalog TO app_credit_analyst, app_service_specialist, app_marketing_analyst,
  app_portfolio_manager, app_compliance_analyst, app_auditor, app_benefits_admin;
