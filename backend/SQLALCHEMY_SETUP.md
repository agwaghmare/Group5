# Local SQLAlchemy schema and role views

**Portfolio workspace:** see [PORTFOLIO_SETUP.md](PORTFOLIO_SETUP.md) for assigned clients, risk assessments and approved simulated rebalancing.


**Current account/AI setup:** see [BESSIE_SETUP.md](BESSIE_SETUP.md). Normal sign-in now requires a provisioned email/password account. Demo login and auto-seeding are disabled; old sample logins below are historical. Bessie uses NVIDIA_API_KEY directly, without AGENT_PROVIDER. Existing financial data remains synthetic.

The active app uses **SQLAlchemy 2 ORM + local SQLite**. SQLAlchemy is the model
and query layer; SQLite stores the data in `backend/storage/finpilot_local.sqlite3`.
No Tiger account, PostgreSQL server, API key, or Lab Package dataset is required.
Existing cloud databases and old local database files were not modified or deleted.

## Start

```sh
cd backend
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage_database.py init
python manage_database.py status
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

The schema and synthetic identities are also initialized on first database-backed
request. Explicit `init` validates/imports the source idempotently. It does not
reset passwords, benefits, decisions or existing audit records. `status` reports
counts and source metadata without printing credentials.

`backend/.env` now has `DATABASE_URL=sqlite:///storage/finpilot_local.sqlite3`.
Paths are resolved relative to backend, regardless of terminal working directory.
Agent keys are preserved and ignored by Git; agents remain explicit mock providers.
The active employee store no longer reads STAFF_DATABASE_URL or Tiger credentials.

## Models and source data

Definitions: `app/orm/models.py`. Engine and SQLite constraints:
`app/orm/database.py`. Validated data import: `app/orm/bootstrap.py`.

| Model/table | Purpose |
| --- | --- |
| Role / roles | Eight Skill.md roles; labels, ordered tabs and features |
| User / users | Unique normalized email, password hash, role FK, active status, optional employee FK |
| Customer / customers | One account per tracker user; source tracker ID linked to User |
| FinanceSnapshot / finance_snapshots | All 44 original CSV columns, composite key (user_id, date), customer FK |
| DataImport / data_imports | Source filename, checksum, column list and row/customer counts |
| Employee / employees | Seeded employee identities, hire dates and role metadata |
| Prospect / prospects | Analyst assignment, application reference and product |
| CreditProfile / credit_profiles | Typed credit fields with prospect FK; blind profile/evaluation input |
| AccessGrant / grants | Analyst/prospect FKs, purpose, reference, expiry and break-glass evidence |
| ResearchRun / runs | Analyst/prospect/grant/policy FKs; immutable evidence and policy snapshot |
| CreditDecision / decisions | Analyst/run FKs, rationale, override flag and immutable human decision |
| HandoffCase, CaseEvent | Assigned consented handoffs and immutable case history |
| BenefitCatalog, BenefitRule, Redemption | Versioned catalog/rules and simulated benefit ledger |
| AuditLog, AuthSession | Append-only audit and revocable hashed opaque sessions |
| ProtectedProfile, EmployeeLink, Permission | Fairness-only labels, conflicts and role feature registry |

Workflow documents retain JSON evidence alongside relational identifiers and typed
research columns. Customers use typed per-column financial data, not one JSON blob.
Uniqueness, foreign keys, role/identity constraints and immutable-record triggers
are enforced by SQLite. Row/field visibility is enforced by server queries; SQLite
does **not** provide PostgreSQL user roles or RLS. Anyone with direct access to the
database file can read it; this is a local synthetic-data prototype.

The only imported finance file is **data/personal_finance_tracker_dataset.csv**:
500 customers, 3,000 snapshots, all 44 columns including user_id and date.
Decimal amounts, source dates, categorical fields and missing values are preserved.
No Lab Package or lab_package_demo profiles/accounts/transactions are read.
Credit Analyst prospects remain the separately labeled reproducible synthetic
fixtures required by Skill.md; policy-only inputs absent from the tracker are not
invented as observations about tracker customers.

## Email login

Local synthetic accounts:

* Customer 1000: `customer1000@example.test` (through customer1499@example.test).
* Analyst E001: `e001@example.test`; second analyst E002: `e002@example.test`.
* Other employees: E003 specialist, E004 marketing, E005 portfolio, E006 compliance,
  E007 auditor, E008 Benefits Admin; emails follow the same pattern.
* Initial demo password: `demo`. Accounts are clearly synthetic, not real emails.

```json
POST /api/v1/auth/login
{"email":"customer1000@example.test","password":"demo"}
```

Response includes `access_token` (also aliased as `token`), user email, role, tabs
and features. Send `Authorization: Bearer <token>` for subsequent requests.
Roles and active status are reread from the database on every request; clients
cannot choose a role during login. No public role-assignment or registration API
is exposed. Use `/api/v1/auth/me` for the current profile and
`DELETE /api/v1/auth/session` to revoke a token.

For a real local email/password on an existing seeded identity:

```sh
python manage_database.py set-user --user-id U1000 --email you@example.com
# Or use --user-id U-E001 for an employee account.
```

Passwords are entered privately and must match with at least 12 characters.
This changes that account's email/password without transferring financial ownership.
There are no outbound confirmation emails or real identity-provider integrations.

The optional demo switcher uses `/api/v1/auth/personas` and
`POST /api/v1/auth/dev-login` with `{"persona_id":"1000"}` or `{"persona_id":"E001"}`.
It is disabled in production or with `DEMO_LOGIN_ENABLED=false`. The older staff
demo login path is retained with `STAFF_DEMO_ENABLED`; both issue the **same token
format** and resolve the same User directory. Disable both switches when you do
not want public demo persona selection. Do not deploy demo accounts publicly.

## Role-specific API views

`GET /api/v1/view` returns the signed-in user's permitted tabs, features, primary
workspace and scoped data. It supplies backend data, not rendered frontend HTML.

| Role | Primary data | Tabs |
| --- | --- | --- |
| customer | Own tracker snapshots, all columns | home, finance, learn |
| credit_analyst | Assigned prospect queue; credit fields require purpose grant | home, research, benefits, activity |
| service_specialist | Assigned cases and consented context | home, cases, benefits, learn |
| marketing_analyst | Campaign results; audience empty without verified consent data | home, portfolio, benefits, learn |
| portfolio_manager | Assigned-client portfolios and own portfolio activity; aggregates suppress groups below five | home, portfolio, benefits, activity |
| compliance_analyst | Overrides, masked research evidence; audit/fairness endpoints | home, compliance, benefits, learn |
| auditor | Read-only audit events | home, compliance, benefits, learn |
| benefits_admin | Benefits ledgers/catalog/rules only | home, benefits, learn |

Customer routes:

* `GET /api/v1/pnc/profile`: latest snapshot with every source field and user identity.
* `GET /api/v1/pnc/tracker` or `/tracker/snapshots`: all own snapshots with column metadata.
* `GET /api/v1/pnc/financial-xray`: limited tracker-derived indicators; no fabricated composite score.
* `GET /api/v1/pnc/cash-flow`: observed monthly tracker income/bills/debt/savings figures.
* `GET /api/v1/pnc/accounts`: reports aggregate balances; individual accounts are unavailable.

The API derives customer ownership from the session. A supplied customer_id cannot
switch ownership. Staff sessions cannot use customer endpoints; personalized Learn
context also requires the same ownership check. Generic lessons remain available.

Credit Analysts continue to use the existing `/staff` endpoints documented in
EMPLOYEE_API.md. Purpose/reference grants expire; conflicts block research;
outside-assignment access needs a typed break-glass reason. Names, age, city and
protected group labels are excluded from analyst profiles and policy inputs.
Research is deterministic pnc-demo-v1 policy; human decisions require rationale,
overrides require reasons, and nothing is sent externally.

## Frontend handoff and retired functionality

No frontend code was changed in this task. Your partner should use email login,
`/api/v1/view` and the tracker schema. Source IDs are **1000–1499**, not the old
Lab Package C001–C030 identities. Those old personas deliberately no longer work.
The pre-existing finance screen may need response/type updates for tracker-only
data; unsupported per-account/transaction/scenario routes are not mounted. The
app does not invent transaction histories to keep those old screens populated.

The same frontend proxy environment remains valid:

```sh
PNC_API_URL=http://127.0.0.1:8010 LEARN_API_URL=http://127.0.0.1:8010 npm run dev
```

Tiger loaders, PostgreSQL migration scripts and Lab pipeline code are archival,
not part of the active app. Do not run old cloud setup instructions. The backend
CI now runs local tests without a cloud migration job.

## Verify

```sh
python -m pytest -q
ruff check app tests scripts manage_database.py
```

`tests/test_sqlalchemy_schema.py` compares every imported field of every snapshot
against the CSV, checks counts/foreign keys/email uniqueness, all eight role views,
unified email-to-employee login, denied cross-customer reads, personalized Learn
isolation, live role/active-status changes, and idempotent import without any Lab
Package reads. Existing employee tests exercise grants, conflicts, decisions,
benefits, audit immutability and policy boundaries on the ORM store.

Archived PostgreSQL/Lab integration tests are skipped in local mode; they are not
evidence for this schema's authorization. The active ORM integration tests run
against real temporary SQLite files and are not skipped.
