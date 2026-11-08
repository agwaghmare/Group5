# Account-based workspaces and live Bessie

Normal sign-in now uses an email/password account with a database-assigned role.
The login page has no persona picker or client-selected role. Employee tabs come
from the server. Customers are redirected away from employee pages and employees
are redirected away from customer finance pages using server identity checks.

## Provision your account first

The old `@example.test` sample accounts are disabled automatically when the normal
app opens its database. Their employee rows, assignments, research and audit
records remain intact. Their sessions are revoked. No password was invented for
you and no account was created using an assumed email address.

To retain E001's existing Credit Analyst queue, adopt that identity locally:

```sh
cd backend
source .venv/bin/activate
python manage_database.py set-user --user-id U-E001 \
  --email your-email@company.com --name "Your Name" --hire-date YYYY-MM-DD
```

Replace the email, name and hire date with the intended values. The command asks
for a password privately, twice; use at least 12 characters. The existing role and
assignments are preserved. It marks the user/employee as an actual provisioned
account while all financial/prospect data and policy remain explicitly synthetic.
The hire date controls benefit calculations. Add `--role portfolio_manager`, for
example, only if you intentionally want to change that employee's access.

To create a separate employee instead:

```sh
python manage_database.py create-employee \
  --email analyst@company.com --name "Analyst Name" \
  --role credit_analyst --hire-date YYYY-MM-DD
```

Use one of the seven staff roles from Skill.md. The result gives the new employee
ID. New employees have an empty work queue until assigned records. To reassign an
existing synthetic prospect without rewriting historical runs or audit entries:

```sh
python manage_database.py assign-prospect --prospect-id P001 --employee-id EMPLOYEE_ID
```

Account provisioning is an operator CLI function, not a public API or a Benefits
Admin privilege. Passwords are hashed; raw passwords are not logged or printed.
Resetting/adopting an account revokes its existing sessions. Customer identities
can be adopted with `set-user --user-id U1000 --email ...`; they remain customers
with the same tracker ownership. No endpoint lets a customer promote their role.

## Environment

Your existing keys are preserved; the adapter reads only NVIDIA_API_KEY, stored in the ignored backend/.env. It only needs:

```dotenv
NVIDIA_API_KEY=YOUR_NVIDIA_API_KEY
# Optional model override; this is also the code default.
NVIDIA_MODEL=nemotron-3.5-super-vl-120b-a12b

DATABASE_URL=sqlite:///storage/finpilot_local.sqlite3
DEMO_LOGIN_ENABLED=false
STAFF_DEMO_ENABLED=false
SEED_DEMO_DATA=false
```

There is no AGENT_PROVIDER switch. There are no required per-agent keys. Demo
fixtures are explicit opt-in for isolated tests, not normal employee onboarding.
Existing shell environment variables override .env; restart the backend after
editing configuration. Never put this key in a VITE_* variable or browser code.

## Start and sign in

```sh
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Open the existing frontend login page and enter your provisioned email/password.
`POST /api/v1/auth/login` returns the session plus the server's role and view
metadata. `/api/v1/auth/me` rechecks the current account; `/staff/me` returns the
employee workspace. The browser uses the returned role, rather than asking you to
select it. Role changes are denied immediately by the backend and the employee UI
refreshes its role metadata periodically and clears old role-scoped query data.

Google sign-in was removed from the normal flow because the old implementation
only decoded a browser token and did not exchange it for a verified application
session. It can be reintroduced later with server verification and account mapping.

## Bessie's prompt and request

Prompt: `app/agents/prompts/bessie.md`, version bessie-v2.
Adapter: `app/agents/bessie.py`. The existing `/staff/assistant` endpoint is live.
Requests default to `agent: "bessie"`; Bessie keeps her identity on every tab.
The explicit staff Explain This panel uses `agent: "wilbur"` with `learn.explain`
and its separate `app/agents/prompts/wilbur.md` prompt (wilbur-v1), inheriting staff
permissions. Customer Amelia and customer Learn's existing deterministic tools
are not silently replaced by this integration.

Greetings and short help requests return an immediate role-scoped application
welcome without calling NVIDIA or retrieving financial evidence. General chat
starts with workspace metadata, not benefits figures. Benefits evidence is used
on the Benefits tab or for an explicit benefits question. A question without a
selected research run receives general help, not an unrelated benefit balance.
Conceptual answers may have no citations; every fact placeholder remains checked.

Nemotron thinking is disabled for concise interactive replies. Provider reads time out after 20 seconds;
the browser cancels after 25 seconds and shows a retry message. Duplicate requests
are disabled while pending; leaving the chat cancels its browser request. Replies
show plain answer text and expandable evidence instead of provider/status badges.

The pipeline authenticates the user, checks role/feature/record scope, computes
or retrieves authorized evidence, calls NVIDIA, then validates the answer. The
provider has no SQL tool, no mutation tool and no ability to choose another URL.
For research, select a prospect, complete the purpose gate and run the policy
engine before asking Bessie about that run. Code computes; Bessie explains.

NVIDIA receives the question, role, feature and a fact map of authorized evidence.
It never receives .env, account passwords or the API key as prompt content. No
unfiltered customer table, excluded credit attributes or cross-role records are
sent. Individual case context must already be consented and assigned.

The model returns structured text with fact placeholders and citations. The
server rejects unknown references, literal numerical claims, malformed outputs
and claims of having performed restricted actions. It renders money/rate values
itself, including cents-to-dollar conversion. Evidence validation is not a proof
of all natural-language semantics; retain human review of recommendations.
The response includes provider/model/prompt version, citations and validation
status. Responses are displayed as plain text, not executable HTML.

SQLite locks are released before the network call. Identity, session, role and
resource access are rechecked before returning an answer, so a role change or
session revocation during the call cannot disclose stale authorized evidence.

## RBAC boundaries

`app/orm/authorization.py` now scopes generic employee reads by role, ownership and
purpose grants, and masks compliance research. `app/orm/metrics.py` exposes
aggregate-only research/fairness queries. Code and database feature grants must
agree. Audit writes, decisions, assignments and caps remain backend operations.
Portfolio and fairness services do not hand raw credit files to an AI agent.

This remains application-enforced authorization over SQLAlchemy/SQLite, not
database-user RLS. Access to the database file or administrative CLI is trusted.

## Errors and verification

Missing keys return 503. Invalid provider credentials/model access return 503.
Provider 429 returns a rate-limit/quota error; timeout returns 504. Invalid model
output returns 502 and is not replaced with a fake successful answer. Upstream
response bodies and credentials are never returned to the frontend.

The adapter uses NVIDIA's fixed HTTPS chat-completions endpoint with Bearer
header authentication. NVIDIA_MODEL accepts the short model name or its full
`nvidia/` prefix; the API always receives the full model ID. JSON answers are
validated locally with the same evidence and role checks. Reasoning content is
never returned to the browser. No Gemini or Mistral key is used as a fallback.
Official model and API example:
https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b .

```sh
python -m pytest -q
ruff check app tests scripts manage_database.py
```

Tests use temporary SQLite databases, explicit demo fixtures and mocked NVIDIA
HTTP responses. They cover normal provisioning, archived sample-account sessions,
role views, central record scope, evidence formatting, denied egress, malformed
answers, provider failures, and role changes while a model request is in flight.
Frontend checks include type checking, login/password/role tests and a production
build. No test suite uses your real key or modifies your normal database.

NVIDIA verification: backend lint and provider-contract tests pass. A live request
with synthetic workspace context used the configured NVIDIA key and
`nvidia/nemotron-3.5-super-vl-120b-a12b`; Bessie replied in 1.79 seconds and passed
evidence validation. No account credentials or customer records were sent. Tests
also check short/full model names, role isolation, separate agent prompts,
unknown citations, timeouts, refusal/truncation and hidden reasoning content.
