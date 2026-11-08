# Employee backend handoff

For the merged customer + employee database setup, see [TIGER_SETUP.md](TIGER_SETUP.md).
Customer DATABASE_URL and employee STAFF_DATABASE_URL serve separate schemas and
login paths; their tokens are not interchangeable.

This is the PNC employee prototype from Skill.md. It extends the existing FastAPI
server without changing any frontend files. All staff data and policy are synthetic.
The API never approves a real application, sends a message, or purchases anything.

## Run locally

From the repository root:

```sh
cd backend
python3 -m venv .venv   # skip if already created
source .venv/bin/activate
python -m pip install -r requirements.txt
# backend/.env already exists locally. On another laptop:
cp .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Open http://127.0.0.1:8010/docs for interactive OpenAPI documentation and request schemas.
The Learn endpoints still exist unchanged. The backend loads `.env` automatically;
shell environment variables take precedence. `.env` and other secret variants are
gitignored; `.env.example` is safe to share. Add your frontend origin to
`CORS_ORIGINS` if it differs from localhost:8080.

With no `STAFF_DATABASE_URL`, staff state persists in `storage/staff.sqlite3`.
This local mode enforces permissions in the API only. It is not proof of database
role isolation. `/staff/me` reports the active mode explicitly.

## Frontend integration

Base URL: `http://127.0.0.1:8010`. With the current Vite `/api` proxy, use
`/api/staff/...` in the browser; Vite strips `/api` before forwarding.

1. `GET /staff/demo/personas` lists the labeled demo personas.
2. `POST /staff/demo/session` with `{"employee_id":"E001"}` returns a bearer token,
   employee details, role-filtered `tabs`, `features`, and the staff disclaimer.
3. Send `Authorization: Bearer <token>` on every subsequent staff request.
4. Call `GET /staff/registry` for tab positions and feature IDs. Do not hard-code
   permissions or use a role supplied by a user as authority.
5. To switch roles, revoke the old token with `DELETE /staff/session`, clear
   role-scoped frontend query caches and selected records, then sign into the
   selected persona. Return Home if the active tab is no longer allowed.

This switcher is demonstration authentication, not real employee identity.
`STAFF_DEMO_ENABLED=false` disables discovery/login. Do not expose demo login
publicly. There is no external identity provider integration yet.

| Persona | Role | Tabs |
| --- | --- | --- |
| E001, E002 | Credit Analyst | home, research, benefits, learn |
| E003 | Service Specialist | home, cases, benefits, learn |
| E004 | Marketing Analyst | home, portfolio, benefits, learn |
| E005 | Portfolio Manager | home, portfolio, benefits, learn |
| E006 | Compliance Analyst | home, compliance, benefits, learn |
| E007 | Auditor | home, compliance, benefits, learn |
| E008 | Benefits Admin | home, benefits, learn |

Session expiry is eight hours by default. Purpose-bound research grants expire
after 15 minutes. Authentication failures return 401; unavailable roles return
403; unavailable resources return 404; invalid bodies return 422; business-rule
conflicts return 409. Errors use FastAPI's `detail` field. Every sensitive read,
mutation, role denial and mock assistant call is audited. Never show API keys.

## Endpoints and workflow

| Endpoint | Purpose / roles |
| --- | --- |
| GET /staff/me | Session profile, tabs, features, storage/provider status |
| GET /staff/registry | Current role's feature IDs and ordered tab positions |
| GET /staff/home | Role-specific greeting and queue counts |
| GET /staff/prospects | Analyst's assigned queue; metadata only, not the credit file |
| POST /staff/access-grants | Analyst: purpose/reference, conflict check, expiry, break-glass |
| GET /staff/prospects/{id}?grant_id=... | Analyst: blind credit profile after purpose gate |
| GET /staff/policies/current | Analyst/compliance/auditor: versioned synthetic policy |
| POST /staff/research-runs | Analyst: evaluate a prospect using an active grant |
| GET /staff/research-runs/{id} | Analyst: own run, active grant required |
| POST /staff/decisions | Analyst: human decision/rationale; override reason required |
| GET /staff/decisions | Analyst: own decisions; compliance: review decisions |
| GET /staff/cases | Specialist: assigned consented handoffs |
| GET /staff/cases/{id} | Specialist: consented context, mock case brief, event history |
| PATCH /staff/cases/{id} | Specialist: note and allowed status transition |
| GET /staff/portfolio | Manager: local finance aggregates and research metrics; marketing: campaign results only |
| GET /staff/benefits | Own tenure tier, cap, ledger, current catalog and rules |
| POST /staff/benefits/redemptions | Own simulated redemption; idempotent request ID |
| GET /staff/benefits/admin/usage | Benefits Admin: benefits-only ledgers and usage |
| POST /staff/benefits/admin/rules | Benefits Admin: new immutable rules version |
| POST /staff/benefits/admin/catalog | Benefits Admin: new immutable item version |
| GET /staff/audit | Auditor/compliance: filter by actor/action/resource/outcome; limit 1–500 |
| GET /staff/compliance/reviews | Compliance: overrides and masked research evidence |
| GET /staff/compliance/fairness | Compliance: recorded-run metrics and measured seed invariance |
| GET /staff/campaigns/audience | Marketing: empty until consent/protection/channel source exists |
| POST /staff/campaigns | Marketing: blocked with 409 while audience is unavailable; never sends |
| GET /staff/compliance/anomalies | Compliance: explicit awaiting-detection-source state |
| POST /staff/assistant | Role-scoped deterministic Bessie/Wilbur placeholder |

### Credit Analyst example

E001 has P001 assigned. P005 demonstrates a conflict of interest. P008 contains
a prompt-injection scenario in the source fixture; notes never enter rule inputs
or the analyst response. P029/P030 are an excluded-input mirror pair.

```json
POST /staff/access-grants
{
  "prospect_id": "P001",
  "purpose": "application_review",
  "reference_id": "APP-001"
}
```

For an unassigned prospect, `break_glass_reason` is also required (10+ characters).
A conflict-of-interest block cannot be bypassed by break-glass. Then:

```json
POST /staff/research-runs
{"grant_id":"<returned grant id>"}
```

Display the result in this order: `outcome`, `rules`, `strengths`/`concerns`,
`missing_inputs`, `indicative_pricing`, `counterfactuals`, then human actions.
Do not preselect a human decision. Outcomes use the required precedence:
DOES_NOT_MEET, INSUFFICIENT_DATA, REFER, MEETS_POLICY.

```json
POST /staff/decisions
{
  "run_id":"<returned run id>",
  "decision":"Proceed to next step (simulated)",
  "rationale":"Reviewed the synthetic evidence and policy checks."
}
```

If the chosen decision differs from `recommended_human_action`, add
`override_reason`. The API records the override for compliance. One decision is
allowed per immutable run; rerun research for a subsequent decision.

Rule evidence is replay-validated before storage. Runs store their policy snapshot,
allowed input snapshot, hash, policy version and data timestamp. Name, age, city,
group labels, benefits and prompt text are excluded. Counterfactuals are returned
only when replaying the full policy proves a better outcome. Empty counterfactuals
mean no supported numerical improvement was found, not that nothing could improve.

### Bessie and Wilbur placeholders

```json
POST /staff/assistant
{
  "feature_id":"staff.creditresearch",
  "resource_id":"<research run id>",
  "question":"Why does this need review?"
}
```

The response explicitly says `provider: mock` and
`status: placeholder_no_external_model`. It returns structured authorized evidence
and a deterministic explanation. Question text is not executed or interpreted by
a live model. The current trace is a code pipeline, not a LangGraph execution.
For `staff.cases`, pass a case ID; `staff.benefits` needs no resource ID.
`learn.explain` with a research run ID explains utilization and debt-to-income
using the analyst's granted run or compliance's masked evidence. Without an ID it
explains benefit math. Existing customer Learn behavior is retained.

Placeholders for Bessie, Amelia, Wilbur and Gemini are in `.env`. Adding keys alone
does not silently activate a model. A future provider adapter must retain the
role gate, numerical validator and no-external-action boundary.

### Benefits and cases

Redemption body: `{"item_id":"B001","quantity":1,"request_id":"unique-client-id"}`.
All prices are integer cents. Use a stable request ID when retrying; reusing it for
different contents returns 409. Tenure uses calendar anniversaries, discounts are
rounded to cents, and partial remaining annual caps trim the discount. Rules and
catalog edits append versions; past ledger entries retain the applied versions.
The business date uses `America/Chicago` by default (`STAFF_TIMEZONE` overrides it).
Discounts never apply to financial products, rates or fees.

Case update: `{"status":"in_progress","note":"Reviewing urgent obligations"}`.
Transitions are new → assigned/in_progress → resolved. Resolved cases cannot be
reopened by this API. Seeded handoffs are explicitly marked; Amelia-to-case creation
is not wired yet. No live customer conversations are read.

## Connect to Tiger later

The runtime defaults to SQLite so your friend can work without cloud credentials.
No migration has been applied to your partner's database by this change.

1. Put an administrative URL in local `STAFF_ADMIN_DATABASE_URL` and run
   `python manage_staff.py init-db`. This explicitly creates only the additive
   `staff_app` schema, synthetic seeds and application roles. It never reloads or
   drops the PNC dataset. The command is transactional and records migration v1.
2. Have the database administrator create a dedicated `LOGIN NOINHERIT` runtime
   user (for example `finpilot_runtime`) and grant `finpilot_gateway` to it.
   Set its password privately, e.g. with psql's `\password finpilot_runtime`.
   Do not grant schema ownership, superuser or BYPASSRLS.
3. Put that runtime user's connection URL in `STAFF_DATABASE_URL` and restart.
   URL-encode reserved characters in passwords. Keep `sslmode=require` for Tiger.
   Do not use `tsdbadmin` as the application runtime credential.
4. The store assumes `finpilot_gateway` for session lookup, then sets the staff
   database role and employee context locally inside each request transaction.
   SQLite serializes requests for cap checks; PostgreSQL takes per-employee
   transaction locks to prevent concurrent cap overruns.
5. Verify the SQL isolation tests against a migrated **dedicated test database**
   using its runtime URL in `STAFF_TEST_DATABASE_URL` before relying on the policies.

The initial PostgreSQL implementation uses regular tables with forced RLS, not
hypertables. Timescale compression/pooler compatibility has not been verified.
The protected-label table has no grants to application roles; only the aggregate
fairness function can read it. Compliance sees a masked research view; portfolio
uses an aggregate-only function. Audit writes use a restricted append function;
updates/deletes/truncation are blocked. Roles receive no access to existing
`pnc` tables through these migrations. The existing PNC dataset is not connected
to role-specific customer reads yet.

## Validation and remaining integration

```sh
python -m unittest discover -s tests -p 'test_staff*.py' -v
python tests/test_learn_api.py
```

The SQLite/API tests cover all seven roles, spoofed roles, grants, conflicts,
expiry, break-glass, decision overrides, audit immutability, benefit caps/limits,
idempotency, cases, policy boundaries, invalid evidence, mirror pairs, and mocks.
Direct PostgreSQL tests skip unless `STAFF_TEST_DATABASE_URL` is supplied.

Remaining work: frontend integration; live model adapters and orchestration;
cloud migration and verified SQL isolation; consented Amelia handoff creation;
verified marketing-consent data; and a fraud detection feed. Portfolio currently uses the **500-user local tracker**,
clearly labeled, rather than inventing the 30-customer cohort mentioned in Skill.md.
No frontend assets, sponsor datasets, or Skill.md registry text were modified.
