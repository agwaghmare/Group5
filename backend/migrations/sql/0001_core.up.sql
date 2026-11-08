-- FinPilot PNC-only core schema. Legacy schemas pnc / staff / meta are left untouched.
CREATE SCHEMA IF NOT EXISTS finpilot;
CREATE SCHEMA IF NOT EXISTS compliance;
SET search_path = finpilot, public;

-- ---------------------------------------------------------------- pipeline bookkeeping
CREATE TABLE bronze_ingestions (
    ingestion_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_name    text NOT NULL,
    source_path     text NOT NULL,
    file_sha256     text NOT NULL,
    source_type     text NOT NULL,
    schema_version  text NOT NULL,
    dataset_version text NOT NULL,
    record_count    integer NOT NULL,
    quarantined_count integer NOT NULL DEFAULT 0,
    status          text NOT NULL CHECK (status IN ('started','succeeded','failed','skipped_duplicate')),
    error           text,
    ingested_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (dataset_name, file_sha256)
);

CREATE TABLE silver_quarantine (
    quarantine_id   bigserial PRIMARY KEY,
    ingestion_id    uuid REFERENCES bronze_ingestions(ingestion_id) ON DELETE CASCADE,
    dataset_name    text NOT NULL,
    row_number      integer,
    reason          text NOT NULL,
    raw             jsonb NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE feature_catalog (
    feature_name    text NOT NULL,
    layer           text NOT NULL CHECK (layer IN ('raw','derived','predicted','scenario')),
    formula         text NOT NULL,
    source_columns  text[] NOT NULL DEFAULT '{}',
    as_of_rule      text NOT NULL,
    version         text NOT NULL,
    PRIMARY KEY (feature_name, version)
);

CREATE TABLE pnc_jobs (
    job_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name        text NOT NULL,
    idempotency_key text NOT NULL UNIQUE,
    status          text NOT NULL CHECK (status IN ('queued','running','succeeded','failed','retrying')),
    attempts        integer NOT NULL DEFAULT 0,
    max_attempts    integer NOT NULL DEFAULT 3,
    scheduled_at    timestamptz NOT NULL DEFAULT now(),
    started_at      timestamptz,
    finished_at     timestamptz,
    error           text,
    result          jsonb
);

-- ---------------------------------------------------------------- customer domain
CREATE TABLE pnc_customers (
    customer_id     text PRIMARY KEY,
    display_name    text NOT NULL,
    age             integer,
    city            text,
    pay_frequency   text NOT NULL CHECK (pay_frequency IN ('weekly','biweekly','semimonthly','monthly')),
    annual_income   numeric(14,2) NOT NULL CHECK (annual_income >= 0),
    income_sources_count integer NOT NULL DEFAULT 1,
    credit_score    integer,
    essential_spending_ratio numeric(6,4),
    savings_rate_assumption numeric(6,4),
    marketing_consent boolean NOT NULL DEFAULT false,
    vulnerable_flag boolean NOT NULL DEFAULT false,
    preferred_channel text CHECK (preferred_channel IN ('email','sms','phone','mail','none')),
    dataset_version text NOT NULL,
    source_type     text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE pnc_accounts (
    account_id      text PRIMARY KEY,
    customer_id     text NOT NULL REFERENCES pnc_customers(customer_id),
    account_type    text NOT NULL CHECK (account_type IN
        ('checking','savings','cd','ira','credit_card','auto_loan','personal_loan','mortgage')),
    name            text NOT NULL,
    opened_date     date NOT NULL,
    balance         numeric(14,2) NOT NULL CHECK (balance >= 0),   -- positive for assets AND liabilities
    apy_pct         numeric(8,4),
    apr_pct         numeric(8,4),
    credit_limit    numeric(14,2),
    original_principal numeric(14,2),
    term_months     integer,
    required_monthly_payment numeric(14,2),
    maturity_date   date,
    dataset_version text NOT NULL,
    source_type     text NOT NULL,
    CHECK (account_type NOT IN ('credit_card') OR credit_limit IS NOT NULL)
);
CREATE INDEX ix_accounts_customer ON pnc_accounts(customer_id);

CREATE TABLE pnc_transactions (
    transaction_id  text NOT NULL,
    posted_date     date NOT NULL,
    customer_id     text NOT NULL,
    account_id      text NOT NULL REFERENCES pnc_accounts(account_id),
    account_type    text NOT NULL,
    transaction_type text NOT NULL,
    category        text NOT NULL,
    description     text,
    amount          numeric(14,2) NOT NULL CHECK (amount >= 0),
    balance_change  numeric(14,2) NOT NULL,
    balance_after   numeric(14,2) NOT NULL,
    flow_class      text NOT NULL CHECK (flow_class IN
        ('income','expense','internal_transfer','external_transfer','non_cash')),
    transfer_id     text,
    source_type     text NOT NULL,
    PRIMARY KEY (transaction_id, posted_date)
);
SELECT create_hypertable('pnc_transactions', 'posted_date', chunk_time_interval => INTERVAL '90 days');
CREATE INDEX ix_txn_customer_date ON pnc_transactions(customer_id, posted_date DESC);
CREATE INDEX ix_txn_account_date ON pnc_transactions(account_id, posted_date DESC);

CREATE TABLE pnc_monthly_statements (
    account_id      text NOT NULL REFERENCES pnc_accounts(account_id),
    statement_month date NOT NULL,
    customer_id     text NOT NULL,
    opening_balance numeric(14,2) NOT NULL,
    closing_balance numeric(14,2) NOT NULL,
    total_increases numeric(14,2) NOT NULL,
    total_decreases numeric(14,2) NOT NULL,
    transaction_count integer NOT NULL,
    source_type     text NOT NULL,
    PRIMARY KEY (account_id, statement_month)
);

CREATE TABLE pnc_balance_history (
    account_id      text NOT NULL REFERENCES pnc_accounts(account_id),
    as_of           date NOT NULL,
    customer_id     text NOT NULL,
    account_type    text NOT NULL,
    balance         numeric(14,2) NOT NULL,
    PRIMARY KEY (account_id, as_of)
);
SELECT create_hypertable('pnc_balance_history', 'as_of', chunk_time_interval => INTERVAL '180 days');

CREATE TABLE pnc_income_history (
    customer_id     text NOT NULL REFERENCES pnc_customers(customer_id),
    month           date NOT NULL,
    income          numeric(14,2) NOT NULL,
    PRIMARY KEY (customer_id, month)
);

CREATE TABLE pnc_recurring_obligations (
    obligation_id   text PRIMARY KEY,
    customer_id     text NOT NULL REFERENCES pnc_customers(customer_id),
    account_id      text REFERENCES pnc_accounts(account_id),
    kind            text NOT NULL CHECK (kind IN ('housing','debt_payment','utility','insurance','subscription','other')),
    monthly_amount  numeric(14,2) NOT NULL CHECK (monthly_amount >= 0),
    due_day         integer CHECK (due_day BETWEEN 1 AND 28),
    origin          text NOT NULL CHECK (origin IN ('account_terms','detected_from_transactions','synthetic_seed','user_entered')),
    evidence        jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ix_obl_customer ON pnc_recurring_obligations(customer_id);

CREATE TABLE pnc_savings_goals (
    goal_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     text NOT NULL REFERENCES pnc_customers(customer_id),
    name            text NOT NULL,
    target_amount   numeric(14,2) NOT NULL CHECK (target_amount > 0),
    starting_amount numeric(14,2) NOT NULL DEFAULT 0,
    current_amount  numeric(14,2) NOT NULL DEFAULT 0,
    deadline        date NOT NULL,
    planned_monthly_contribution numeric(14,2),
    constraints     jsonb NOT NULL DEFAULT '{}',
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','abandoned')),
    last_plan       jsonb,
    last_recalculated_at timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_goals_customer ON pnc_savings_goals(customer_id);

CREATE TABLE pnc_health_snapshots (
    customer_id     text NOT NULL,
    as_of           date NOT NULL,
    features        jsonb NOT NULL,
    indicators      jsonb NOT NULL,
    engine_version  text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (customer_id, as_of, engine_version)
);
SELECT create_hypertable('pnc_health_snapshots', 'as_of', chunk_time_interval => INTERVAL '180 days');

CREATE TABLE pnc_forecast_results (
    forecast_id     uuid NOT NULL DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    customer_id     text NOT NULL,
    kind            text NOT NULL,
    horizon         text NOT NULL,
    evidence        jsonb NOT NULL,
    PRIMARY KEY (forecast_id, created_at)
);
SELECT create_hypertable('pnc_forecast_results', 'created_at', chunk_time_interval => INTERVAL '30 days');
CREATE INDEX ix_forecast_customer ON pnc_forecast_results(customer_id, created_at DESC);

CREATE TABLE pnc_financial_scenarios (
    scenario_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     text NOT NULL REFERENCES pnc_customers(customer_id),
    kind            text NOT NULL,
    label           text NOT NULL,
    inputs          jsonb NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_scen_customer ON pnc_financial_scenarios(customer_id, created_at DESC);

CREATE TABLE pnc_scenario_results (
    result_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario_id     uuid NOT NULL REFERENCES pnc_financial_scenarios(scenario_id) ON DELETE CASCADE,
    customer_id     text NOT NULL,
    evidence        jsonb NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE pnc_debt_plans (
    plan_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     text NOT NULL REFERENCES pnc_customers(customer_id),
    strategy        text NOT NULL,
    inputs          jsonb NOT NULL,
    evidence        jsonb NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE pnc_fraud_events (
    event_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     text NOT NULL REFERENCES pnc_customers(customer_id),
    transaction_id  text NOT NULL,
    posted_date     date NOT NULL,
    detector        text NOT NULL,
    anomaly_score   numeric(10,6),
    review_flag     boolean NOT NULL DEFAULT true,
    model_version   text NOT NULL,
    supporting_factors jsonb NOT NULL DEFAULT '{}',
    source_type     text NOT NULL,
    -- an anomaly is NOT confirmed fraud: 'confirmed_fraud' requires a verified human review
    review_status   text NOT NULL DEFAULT 'open' CHECK (review_status IN
        ('open','in_review','dismissed','escalated','confirmed_by_human_review')),
    reviewed_by     text,
    reviewed_at     timestamptz,
    review_note     text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (transaction_id, detector, model_version),
    CHECK (review_status <> 'confirmed_by_human_review' OR reviewed_by IS NOT NULL)
);
CREATE INDEX ix_fraud_customer ON pnc_fraud_events(customer_id);

CREATE TABLE pnc_fraud_cases (
    case_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     text NOT NULL REFERENCES pnc_customers(customer_id),
    transaction_id  text,
    reason          text NOT NULL,
    description     text,
    status          text NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted','under_review','closed')),
    simulated       boolean NOT NULL DEFAULT true CHECK (simulated),
    service_case_id uuid,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_fraudcase_customer ON pnc_fraud_cases(customer_id);

CREATE TABLE pnc_fraud_case_history (
    history_id      bigserial PRIMARY KEY,
    case_id         uuid NOT NULL REFERENCES pnc_fraud_cases(case_id) ON DELETE CASCADE,
    customer_id     text NOT NULL,
    from_status     text,
    to_status       text NOT NULL,
    note            text,
    recorded_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE pnc_consents (
    customer_id     text NOT NULL REFERENCES pnc_customers(customer_id),
    scope           text NOT NULL CHECK (scope IN ('marketing','case_context_sharing','data_sharing')),
    granted         boolean NOT NULL,
    updated_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (customer_id, scope)
);

-- ---------------------------------------------------------------- employee domain
CREATE TABLE employees (
    employee_id     text PRIMARY KEY,
    display_name    text NOT NULL,
    role            text NOT NULL CHECK (role IN ('credit_analyst','service_specialist','marketing_analyst',
                        'portfolio_manager','compliance_analyst','auditor','benefits_admin')),
    org             text NOT NULL DEFAULT 'pnc' CHECK (org = 'pnc'),
    hire_date       date NOT NULL,
    household_id    text,
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
    source_type     text NOT NULL
);

CREATE TABLE employee_links (
    employee_id     text NOT NULL REFERENCES employees(employee_id),
    linked_kind     text NOT NULL CHECK (linked_kind IN ('prospect','customer')),
    linked_id       text NOT NULL,
    relation        text NOT NULL CHECK (relation IN ('self','household','family','close_associate')),
    PRIMARY KEY (employee_id, linked_kind, linked_id)
);

CREATE TABLE role_permissions (
    role            text NOT NULL,
    feature_id      text NOT NULL,
    scope           text NOT NULL,
    PRIMARY KEY (role, feature_id)
);

CREATE TABLE prospects (
    prospect_id     text PRIMARY KEY,
    product         text NOT NULL CHECK (product IN ('personal_loan','credit_card')),
    application_ref text NOT NULL UNIQUE,
    assigned_to     text REFERENCES employees(employee_id),
    status          text NOT NULL DEFAULT 'open',
    -- excluded attributes (never inputs to the policy engine, hidden in blind review)
    display_name    text NOT NULL,
    age             integer,
    city            text,
    zip             text,
    marital_status  text,
    mirror_group    text,
    scenario_tag    text NOT NULL,
    source_type     text NOT NULL
);

CREATE TABLE prospect_credit_profile (
    prospect_id     text PRIMARY KEY REFERENCES prospects(prospect_id),
    employment_months integer,
    income_verified text CHECK (income_verified IN ('Y','N','unknown')),
    annual_income   numeric(14,2),
    credit_band     text CHECK (credit_band IN ('Excellent','Good','Fair','Poor')),
    credit_score    integer,
    revolving_balance numeric(14,2),
    revolving_limit numeric(14,2),
    existing_monthly_debt numeric(14,2),
    delinquencies_12m integer,
    delinquencies_24m integer,
    bankruptcy_years_ago numeric(5,1),
    history_months  integer,
    inquiries_6m    integer,
    requested_amount numeric(14,2),
    term_months     integer,
    requested_limit numeric(14,2),
    notes           text,
    source_type     text NOT NULL
);

CREATE TABLE compliance.prospect_protected (
    prospect_id     text PRIMARY KEY REFERENCES prospects(prospect_id),
    group_label     text NOT NULL,
    source_type     text NOT NULL DEFAULT 'synthetic_group_label'
);

CREATE TABLE credit_policies (
    policy_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    version         integer NOT NULL UNIQUE,
    name            text NOT NULL,
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),
    allowlist       text[] NOT NULL,
    rules           jsonb NOT NULL,
    disclaimer      text NOT NULL,
    created_by      text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE access_grants (
    grant_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    analyst_id      text NOT NULL REFERENCES employees(employee_id),
    prospect_id     text NOT NULL REFERENCES prospects(prospect_id),
    purpose         text NOT NULL CHECK (length(trim(purpose)) >= 5),
    application_ref text NOT NULL,
    state           text NOT NULL DEFAULT 'active' CHECK (state IN ('active','revoked')),
    break_glass     boolean NOT NULL DEFAULT false,
    break_glass_reason text,
    authorized_by   text REFERENCES employees(employee_id),
    created_at      timestamptz NOT NULL DEFAULT now(),
    expires_at      timestamptz NOT NULL,
    CHECK (NOT break_glass OR length(trim(coalesce(break_glass_reason,''))) >= 20)
);
CREATE INDEX ix_grants_analyst ON access_grants(analyst_id, prospect_id);

CREATE TABLE credit_research_runs (
    run_id          uuid NOT NULL DEFAULT gen_random_uuid(),
    run_at          timestamptz NOT NULL DEFAULT now(),
    prospect_id     text NOT NULL,
    analyst_id      text NOT NULL,
    grant_id        uuid NOT NULL,
    policy_version  integer NOT NULL,
    input_snapshot  jsonb NOT NULL,
    input_hash      text NOT NULL,
    rule_results    jsonb NOT NULL,
    outcome         text NOT NULL CHECK (outcome IN ('DOES_NOT_MEET','INSUFFICIENT_DATA','REFER','MEETS_POLICY')),
    missing_inputs  jsonb NOT NULL DEFAULT '[]',
    pricing_tier    text,
    evidence        jsonb NOT NULL,
    PRIMARY KEY (run_id, run_at)
);
SELECT create_hypertable('credit_research_runs', 'run_at', chunk_time_interval => INTERVAL '30 days');
CREATE INDEX ix_runs_run ON credit_research_runs(run_id);
CREATE INDEX ix_runs_prospect ON credit_research_runs(prospect_id, run_at DESC);

CREATE TABLE credit_decisions (
    decision_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          uuid NOT NULL,        -- no FK: credit_research_runs is a hypertable
    prospect_id     text NOT NULL,
    analyst_id      text NOT NULL REFERENCES employees(employee_id),
    decision        text NOT NULL CHECK (decision IN ('proceed_simulated','request_more_information',
                        'refer_senior_review','decline_as_entered')),
    rationale       text NOT NULL CHECK (length(trim(rationale)) >= 10),
    reason_codes    text[] NOT NULL DEFAULT '{}',
    policy_version  integer NOT NULL,
    engine_outcome  text NOT NULL,
    is_override     boolean NOT NULL,
    override_reason text,
    supersedes_decision_id uuid REFERENCES credit_decisions(decision_id),
    decided_at      timestamptz NOT NULL DEFAULT now(),
    CHECK (NOT is_override OR length(trim(coalesce(override_reason,''))) >= 10),
    CHECK (decision <> 'decline_as_entered' OR cardinality(reason_codes) >= 1)
);
CREATE INDEX ix_decisions_run ON credit_decisions(run_id);

CREATE TABLE cases (
    case_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     text NOT NULL REFERENCES pnc_customers(customer_id),
    org             text NOT NULL DEFAULT 'pnc' CHECK (org = 'pnc'),
    source          text NOT NULL CHECK (source IN ('hardship_request','transaction_report',
                        'fraud_anomaly_investigation','financial_counseling_handoff','other')),
    reason          text NOT NULL,
    consented_context jsonb NOT NULL DEFAULT '{}',
    assigned_to     text REFERENCES employees(employee_id),
    status          text NOT NULL DEFAULT 'new' CHECK (status IN ('new','assigned','in_progress','resolved')),
    sla_due         timestamptz NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CHECK ((status = 'new' AND assigned_to IS NULL) OR (status <> 'new' AND assigned_to IS NOT NULL))
);
CREATE INDEX ix_cases_assigned ON cases(assigned_to, status);
CREATE INDEX ix_cases_customer ON cases(customer_id);

CREATE TABLE case_events (
    event_id        uuid NOT NULL DEFAULT gen_random_uuid(),
    event_at        timestamptz NOT NULL DEFAULT now(),
    case_id         uuid NOT NULL,
    actor_id        text NOT NULL,
    event_type      text NOT NULL CHECK (event_type IN ('created','note','status_change','assignment')),
    from_status     text,
    to_status       text,
    note            text,
    PRIMARY KEY (event_id, event_at)
);
SELECT create_hypertable('case_events', 'event_at', chunk_time_interval => INTERVAL '90 days');
CREATE INDEX ix_case_events_case ON case_events(case_id, event_at);

CREATE TABLE portfolio_snapshots (
    snapshot_id     bigserial PRIMARY KEY,
    as_of           date NOT NULL,
    metric_key      text NOT NULL,
    dimension       text NOT NULL DEFAULT 'all',
    group_key       text NOT NULL DEFAULT 'all',
    group_size      integer NOT NULL,
    suppressed      boolean NOT NULL,
    suppression_reason text,
    value           jsonb,
    source_type     text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CHECK (NOT suppressed OR value IS NULL)
);
CREATE INDEX ix_portfolio_metric ON portfolio_snapshots(metric_key, as_of);

CREATE TABLE campaigns (
    campaign_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_by      text NOT NULL REFERENCES employees(employee_id),
    name            text NOT NULL,
    criteria        jsonb NOT NULL,
    eligible_count  integer NOT NULL,
    suppression     jsonb NOT NULL,
    simulated       boolean NOT NULL DEFAULT true CHECK (simulated),
    results         jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE benefit_catalog (
    item_id         text NOT NULL,
    version         integer NOT NULL,
    name            text NOT NULL,
    category        text NOT NULL CHECK (category IN ('merchandise','partner_merchandise')),
    list_price      numeric(10,2) NOT NULL CHECK (list_price > 0),
    discount_eligible boolean NOT NULL DEFAULT true,
    active          boolean NOT NULL DEFAULT true,
    created_by      text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (item_id, version)
);

CREATE TABLE benefit_rules (
    rule_version    integer PRIMARY KEY,
    tiers           jsonb NOT NULL,
    annual_cap      numeric(10,2) NOT NULL CHECK (annual_cap > 0),
    per_item_quarter_limit integer NOT NULL CHECK (per_item_quarter_limit > 0),
    excluded_categories text[] NOT NULL,
    created_by      text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE benefit_redemptions (
    redemption_id   uuid NOT NULL DEFAULT gen_random_uuid(),
    redeemed_at     timestamptz NOT NULL DEFAULT now(),
    employee_id     text NOT NULL,
    item_id         text NOT NULL,
    item_version    integer NOT NULL,
    rule_version    integer NOT NULL,
    quantity        integer NOT NULL CHECK (quantity > 0),
    list_price      numeric(10,2) NOT NULL,
    applied_discount numeric(10,2) NOT NULL,
    final_price     numeric(10,2) NOT NULL,
    remaining_cap   numeric(10,2) NOT NULL,
    voucher_code    text NOT NULL,
    simulated       boolean NOT NULL DEFAULT true CHECK (simulated),
    PRIMARY KEY (redemption_id, redeemed_at)
);
SELECT create_hypertable('benefit_redemptions', 'redeemed_at', chunk_time_interval => INTERVAL '180 days');
CREATE INDEX ix_redemptions_employee ON benefit_redemptions(employee_id, redeemed_at DESC);

CREATE TABLE audit_log (
    audit_id        uuid NOT NULL DEFAULT gen_random_uuid(),
    ts              timestamptz NOT NULL DEFAULT now(),
    actor_id        text NOT NULL,
    role            text NOT NULL,
    org             text NOT NULL DEFAULT 'pnc',
    action          text NOT NULL,
    resource        text,
    purpose         text,
    grant_id        text,
    result          text NOT NULL CHECK (result IN ('allowed','denied','error')),
    break_glass     boolean NOT NULL DEFAULT false,
    request_id      text,
    detail          jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (audit_id, ts)
);
SELECT create_hypertable('audit_log', 'ts', chunk_time_interval => INTERVAL '30 days');
CREATE INDEX ix_audit_actor ON audit_log(actor_id, ts DESC);
CREATE INDEX ix_audit_action ON audit_log(action, ts DESC);
