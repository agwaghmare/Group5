# Tiger and AI setup after merging archit

The merged backend includes the customer finance API from archit, the existing
Learn API and the employee API. No shared cloud schema/data was changed during
the merge. Existing local .env values were preserved, missing customer settings
were appended, and a random local JWT_SECRET was generated.

## 1. Configure customer database access

Edit backend/.env privately. Never commit it or paste passwords into chat.

```dotenv
APP_ENV=dev
DATABASE_URL=postgresql+psycopg://USER:ENCODED_PASSWORD@HOST:PORT/tsdb?sslmode=require
DEMO_LOGIN_ENABLED=true
```

Use the current service connection details supplied by your partner. If the service
has not changed, the previously shared host is
ernvuaxenn.hx4gme5c8i.tsdb.cloud.timescale.com and port 34969; verify with your partner.
Encode reserved password characters as URL components. The customer SQLAlchemy
adapter accepts postgresql:// and postgres:// URLs too and normalizes them.

DATABASE_URL currently serves customer migrations, CLI/pipeline jobs, user lookup,
and role-scoped customer queries. Use an account authorized for those operations
in this local demo. This customer adapter does not yet split administrative and
runtime URLs like the employee adapter does. Do not expose the demo publicly.

```sh
cd backend
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/probe_db.py
python -m alembic current
python -m alembic heads
```

These commands inspect the configured database; they do not apply migrations.
The customer Alembic history currently ends at 0005_app_users. Confirm with your
partner that this is the database they prepared. If already at head, do not reload
datasets or reseed users. If behind, the migration owner can run:

```sh
python -m alembic upgrade head
```

This step changes schema, roles, functions and views. It is not a data download.
If schemas already exist but Alembic has no matching version, have your partner
reconcile migration history instead of blindly stamping or recreating tables.

After the schema is verified, inspect the actual data:

```sh
python -m app.cli data status
python -m app.cli data reconcile
```

These are inspection/reconciliation commands. They do not ingest or regenerate
the partner's data. A connection to the same service gives both laptops access
to the same cloud rows; no local database copy is required.

If the database has not been prepared, your partner should provision its demo
data and app_users using the CLI. Ingestion, build-features and seed-users are
mutating operations; do not run them merely to test connectivity. In particular,
seed-users can reset the shared demo password.

## 2. Configure the employee database separately

```dotenv
STAFF_ADMIN_DATABASE_URL=postgresql://ADMIN:ENCODED_PASSWORD@HOST:PORT/tsdb?sslmode=require
STAFF_DATABASE_URL=postgresql://finpilot_runtime:ENCODED_PASSWORD@HOST:PORT/tsdb?sslmode=require
STAFF_DEMO_ENABLED=true
```

Unlike DATABASE_URL, these two URLs go directly to psycopg: do not include
the +psycopg SQLAlchemy suffix. Both can point at the same Tiger service as the
customer API, but employee data lives in staff_app rather than finpilot.

First have the migration owner check whether staff_app.schema_migrations already
contains staff-v1. If not, apply the additive employee migration:

```sh
python manage_staff.py init-db
```

It creates the separate employee schema, RLS roles/policies and synthetic employee
fixtures. It does not migrate the existing finpilot employees into staff_app.
Avoid the older load_tiger_datasets.py script for setup: it drops/recreates data.

The administrator then provisions the dedicated employee runtime account:

```sql
CREATE ROLE finpilot_runtime LOGIN NOINHERIT;
GRANT finpilot_gateway TO finpilot_runtime;
```

If that role already exists, inspect/reuse it rather than recreating it.
Set its password privately in psql with `\password finpilot_runtime`. Do not grant
schema ownership, superuser or BYPASSRLS. STAFF_DATABASE_URL must use this runtime
credential; the employee adapter rejects a migration owner or privileged login.
Leaving STAFF_DATABASE_URL empty intentionally retains local SQLite.

## 3. Run one backend and verify both paths

```sh
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Restart an already-running backend to load the merged routes and environment.
Use http://127.0.0.1:8010/docs to inspect the API:

* GET /health checks the process.
* GET /health/db checks the **customer** DATABASE_URL connection only.
* GET /api/v1/auth/personas lists cloud customer/new-schema personas. Demo login
  uses POST /api/v1/auth/dev-login with {"persona_id":"C001"}; its token field is
  access_token. This requires the partner's app_users to be seeded.
* GET /staff/demo/personas and POST /staff/demo/session with {"employee_id":"E001"}
  are the **employee** login. Its token field is token. Use that bearer token for
  GET /staff/me and check that storage is postgresql_rls.

These two tokens, employee ID sets and login paths are not interchangeable.
The merged cloud user directory's staff personas do not automatically sign into
the separate employee API. Shared identity/schema integration remains future work.

From a second terminal, the merged frontend can point both proxies at the single
backend without editing any frontend source:

```sh
cd frontend
PNC_API_URL=http://127.0.0.1:8010 LEARN_API_URL=http://127.0.0.1:8010 npm run dev
```

Run this from the repository root (or adjust cd relative to your current folder).
The merged frontend otherwise defaults customer requests to :8002 and Learn/staff
requests to :8010. Backend/.env is not automatically loaded by the frontend Vite
process, so use its shell environment for these proxy URLs.

Run backend checks with `python -m pytest -q`. Tests requiring a live customer DB
skip when no connection is available. For the employee direct SQL checks, set
STAFF_TEST_DATABASE_URL to a migrated **dedicated test database's runtime URL**.
Passing /health/db alone does not establish that either permission system is correct.

## 4. AI keys

Keep the existing placeholders in backend/.env until you have the provider keys:

```dotenv
AGENT_PROVIDER=mock
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
BESSIE_API_KEY=YOUR_BESSIE_API_KEY
AMELIA_API_KEY=YOUR_AMELIA_API_KEY
WILBUR_API_KEY=YOUR_WILBUR_API_KEY
```

These agent names are app roles, not necessarily separate provider accounts or
keys. If all agents use the same provider, one provider credential can support
multiple agent configurations. Keep all credentials on the backend.

Neither merged branch currently contains a live Gemini/other LLM client or agent
provider adapter. Adding a key or changing AGENT_PROVIDER alone will not activate
an agent. The next implementation task is a backend adapter that chooses a model,
receives only role-authorized evidence, validates structured output and numerical
claims, and reports provider errors honestly. Until then /staff/assistant explicitly
remains mock. Bessie uses the employee session and tool allowlist; Amelia needs
customer identity; Wilbur must inherit the calling user's permitted context.

The partner's cash-flow/anomaly model code is numerical ML, not a Bessie/Amelia
chat provider integration. No AI key is needed just to connect to Tiger.
